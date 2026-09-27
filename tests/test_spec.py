"""Instance specs: what the privileged helper accepts. A spec names one engine, one pinned image,
one model snapshot from the store and a whitelisted set of engine arguments; anything else is
refused, because the helper turns it into a root `docker run`."""
import unittest

from raytone_models import spec

DIGEST = "sha256:" + "a" * 64
SNAPSHOT = "models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/" + "0" * 40


def good(**over):
    s = {
        "id": "qwen38-27b",
        "engine": "vllm",
        "image": f"vllm/vllm-openai@{DIGEST}",
        "model": SNAPSHOT,
        "served_name": "qwen3.8-27b",
        "port": 18001,
        "args": {"gpu-memory-utilization": 0.6, "max-model-len": 131072, "enable-prefix-caching": True,
                 "reasoning-parser": "qwen3", "tool-call-parser": "qwen3_coder", "enable-auto-tool-choice": True},
        "env": {},
    }
    s.update(over)
    return s


class SpecTests(unittest.TestCase):
    def test_a_good_spec_loads(self):
        s = spec.load(good())
        self.assertEqual((s.id, s.engine, s.port, s.served_name), ("qwen38-27b", "vllm", 18001, "qwen3.8-27b"))

    def refused(self, why, **over):
        with self.assertRaises(spec.SpecError, msg=why):
            spec.load(good(**over))

    def test_identity_fields(self):
        self.refused("id with a slash", id="../x")
        self.refused("id too long", id="a" * 65)
        self.refused("unknown engine", engine="bash")
        self.refused("served name with a space", served_name="qwen 27b")

    def test_images_are_pinned_and_known(self):
        self.refused("a tag, not a digest", image="vllm/vllm-openai:v0.30.0")
        self.refused("a registry not allowed", image=f"evil.example/vllm@{DIGEST}")
        self.refused("a short digest", image="vllm/vllm-openai@sha256:abc")
        self.refused("an sglang image for vllm", image=f"nvcr.io/nvidia/sglang@{DIGEST}")

    def test_the_model_is_a_store_snapshot(self):
        self.refused("absolute path", model="/etc")
        self.refused("path traversal", model="models--a--b/snapshots/../../../etc")
        self.refused("not a snapshot", model="models--a--b/blobs/x")

    def test_ports_stay_in_the_instance_range(self):
        self.refused("privileged port", port=22)
        self.refused("router port", port=8090)
        self.refused("not an int", port="18001")

    def test_only_whitelisted_arguments(self):
        self.refused("an unknown flag", args={"load-format": "pt"})
        self.refused("a flag smuggling a second one", args={"reasoning-parser": "qwen3 --trust-remote-code"})
        self.refused("a value that is itself an option", args={"tool-call-parser": "--trust-remote-code"})
        self.refused("out of range", args={"gpu-memory-utilization": 1.5})
        self.refused("wrong type", args={"max-model-len": "131072"})
        self.refused("json that is not an object", args={"speculative-config": "[1]"})

    def test_env_only_for_the_engine(self):
        self.refused("a loader variable", env={"LD_PRELOAD": "/x.so"})
        self.refused("a value with a space", env={"VLLM_PLE_MMAP": "1 2"})
        self.assertEqual(spec.load(good(env={"VLLM_PLE_MMAP": "1"})).env, {"VLLM_PLE_MMAP": "1"})

    def test_unknown_top_level_keys_are_refused(self):
        with self.assertRaises(spec.SpecError):
            spec.load({**good(), "volumes": ["/:/host"]})


if __name__ == "__main__":
    unittest.main()
