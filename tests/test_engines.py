"""Engine adapters turn a validated spec into the exact `docker run` argv the helper executes."""
import unittest

from raytone_models import engines, spec
from tests.test_spec import DIGEST, DRAFT, H3, SNAPSHOT, comfyui, good, sglang


class VllmTests(unittest.TestCase):
    def argv(self, **over):
        return engines.docker_argv(spec.load(good(**over)), store="/srv/hf", cache="/var/cache/raytone-models/qwen38-27b",
                                   user=(961, 961), groups=(983, 987))

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
        # nothing is ever pulled at start: offline at a show, and no surprise downloads
        self.assertIn("--pull=never", a)

    def test_the_engine_runs_unprivileged(self):
        # From Codex's review: a root container with a writable host cache could leave a root-owned
        # setuid file for the user to run. The engine runs as its own user, with no capabilities.
        a = self.argv()
        self.assertIn("--user=961:961", a)
        self.assertIn("--group-add=983", a)          # /dev/nvmap, /dev/dri/card* (video)
        self.assertIn("--group-add=987", a)          # /dev/dri/renderD* (render)
        self.assertIn("--cap-drop=ALL", a)
        self.assertIn("--security-opt=no-new-privileges", a)
        self.assertIn("--env=HOME=/cache", a)
        self.assertLess(a.index("--user=961:961"), a.index(f"vllm/vllm-openai@{DIGEST}"))

    def test_root_is_never_the_engine_user(self):
        with self.assertRaises(ValueError):
            engines.docker_argv(spec.load(good()), store="/srv/hf", cache="/c", user=(0, 0), groups=())

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



class SglangTests(unittest.TestCase):
    def argv(self, **over):
        return engines.docker_argv(spec.load(sglang(**over)), store="/srv/hf", cache="/var/cache/raytone-models/n",
                                   user=(961, 961), groups=(983, 987))

    def test_same_confinement_as_vllm(self):
        a = self.argv()
        for flag in ("--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=961:961",
                     "--device=nvidia.com/gpu=all", "--publish=127.0.0.1:18001:8000", "--volume=/srv/hf:/hf:ro",
                     "--env=HF_HUB_OFFLINE=1", "--env=HOME=/cache"):
            self.assertIn(flag, a)
        for bad in ("--network=host", "--ipc=host", "--privileged"):
            self.assertNotIn(bad, a)

    def test_the_user_has_a_name_without_a_passwd_entry(self):
        # seen on the Thor: torch's compiler asks getpass.getuser(), and uid 955 has no passwd entry
        # in the image; getpass reads LOGNAME and USER first
        a = self.argv()
        self.assertIn("--env=USER=raytone-engine", a)
        self.assertIn("--env=LOGNAME=raytone-engine", a)

    def test_launch_server_with_the_model_and_metrics(self):
        a = self.argv()
        rest = a[a.index(f"nvcr.io/nvidia/sglang@{DIGEST}") + 1:]
        self.assertEqual(rest[:3], ["python3", "-m", "sglang.launch_server"])
        self.assertEqual(rest[rest.index("--model-path") + 1], "/hf/hub/" + SNAPSHOT)
        self.assertEqual(rest[rest.index("--served-model-name") + 1], "qwen3.8-27b")
        self.assertEqual(rest[rest.index("--port") + 1], "8000")
        self.assertIn("--enable-metrics", rest)     # the Running page's tokens/s
        self.assertEqual(rest[rest.index("--speculative-draft-model-path") + 1], DRAFT)
        self.assertEqual(rest[rest.index("--speculative-dspark-block-size") + 1], "3")
        self.assertIn("--env=SGLANG_ENABLE_SPEC_V2=1", a)

    def test_the_health_url_is_the_same(self):
        self.assertEqual(engines.health_url(spec.load(sglang())), "http://127.0.0.1:18001/v1/models")



class ComfyuiTests(unittest.TestCase):
    def argv(self, **over):
        return engines.docker_argv(spec.load(comfyui(**over)), store="/srv/hf", cache="/var/cache/raytone-models/h3",
                                   user=(961, 961), groups=(983, 987))

    def test_same_confinement(self):
        a = self.argv()
        for flag in ("--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=961:961",
                     "--device=nvidia.com/gpu=all", "--publish=127.0.0.1:18001:8000", "--volume=/srv/hf:/hf:ro",
                     "--env=HF_HUB_OFFLINE=1", "--env=HOME=/cache"):
            self.assertIn(flag, a)

    def test_the_local_image_runs_by_its_id(self):
        # built on this machine (scripts/build-engine), so it has no registry digest: the image ID
        # pins it just as firmly
        a = self.argv()
        self.assertIn(f"{DIGEST}", a)
        self.assertNotIn(f"raytone/comfyui@{DIGEST}", a)

    def test_the_launcher_gets_the_snapshot_and_flags(self):
        a = self.argv()
        rest = a[a.index(DIGEST) + 1:]
        self.assertEqual(rest[:5], ["raytone-comfyui", "--models", "/hf/hub/" + H3, "--port", "8000"])
        self.assertIn("--gpu-only", rest)
        self.assertEqual(rest[rest.index("--reserve-vram") + 1], "2.0")

    def test_health_is_comfyui_own(self):
        self.assertEqual(engines.health_url(spec.load(comfyui())), "http://127.0.0.1:18001/system_stats")


if __name__ == "__main__":
    unittest.main()
