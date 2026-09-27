"""Engine adapters turn a validated spec into the exact `docker run` argv the helper executes."""
import unittest

from raytone_models import engines, spec
from tests.test_spec import DIGEST, SNAPSHOT, good


class VllmTests(unittest.TestCase):
    def argv(self, **over):
        return engines.docker_argv(spec.load(good(**over)), store="/srv/hf", cache="/var/cache/raytone-models/qwen38-27b")

    def test_container_is_confined(self):
        a = self.argv()
        self.assertEqual(a[:4], ["docker", "run", "--rm", "--name"])
        self.assertIn("raytone-qwen38-27b", a)
        # the GPU through CDI, the port only on loopback, the store read-only
        self.assertIn("--device=nvidia.com/gpu=all", a)
        self.assertIn("--publish=127.0.0.1:18001:8000", a)
        self.assertIn("--volume=/srv/hf:/hf:ro", a)
        self.assertIn("--volume=/var/cache/raytone-models/qwen38-27b:/cache", a)
        for bad in ("--privileged", "--network=host", "--ipc=host", "--pid=host"):
            self.assertNotIn(bad, a)
        self.assertIn("--env=HF_HUB_OFFLINE=1", a)

    def test_image_then_vllm_arguments(self):
        a = self.argv()
        i = a.index(f"vllm/vllm-openai@{DIGEST}")
        rest = a[i + 1:]
        self.assertEqual(rest[:3], ["/hf/hub/" + SNAPSHOT, "--served-model-name", "qwen3.8-27b"])
        self.assertIn("--host", rest)
        self.assertEqual(rest[rest.index("--port") + 1], "8000")
        self.assertEqual(rest[rest.index("--gpu-memory-utilization") + 1], "0.6")
        self.assertIn("--enable-prefix-caching", rest)
        self.assertEqual(rest[rest.index("--tool-call-parser") + 1], "qwen3_coder")

    def test_json_arguments_are_compact_json(self):
        a = self.argv(args={"speculative-config": {"method": "mtp", "num_speculative_tokens": 3}})
        self.assertEqual(a[a.index("--speculative-config") + 1], '{"method":"mtp","num_speculative_tokens":3}')

    def test_engine_env_is_passed(self):
        self.assertIn("--env=VLLM_PLE_MMAP=1", self.argv(env={"VLLM_PLE_MMAP": "1"}))

    def test_health_url(self):
        self.assertEqual(engines.health_url(spec.load(good())), "http://127.0.0.1:18001/v1/models")


if __name__ == "__main__":
    unittest.main()
