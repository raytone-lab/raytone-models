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


DRAFT = "/hf/hub/models--nvidia--NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark/snapshots/" + "8" * 40


def sglang(**over):
    s = good(engine="sglang", image=f"nvcr.io/nvidia/sglang@{DIGEST}",
             args={"mem-fraction-static": 0.6, "context-length": 262144, "mamba-ssm-dtype": "float16",
                   "reasoning-parser": "nemotron_3", "tool-call-parser": "qwen3_coder",
                   "speculative-algorithm": "DSPARK", "speculative-draft-model-path": DRAFT,
                   "speculative-dspark-block-size": 3, "kv-cache-dtype": "fp8_e4m3"},
             env={"SGLANG_ENABLE_SPEC_V2": "1"})
    s.update(over)
    return s


class SglangSpecTests(unittest.TestCase):
    def test_a_good_sglang_spec_loads(self):
        s = spec.load(sglang())
        self.assertEqual(s.engine, "sglang")
        spec.load(sglang(image=f"lmsysorg/sglang@{DIGEST}"))

    def refused(self, why, **over):
        with self.assertRaises(spec.SpecError, msg=why):
            spec.load(sglang(**over))

    def test_images_and_arguments_are_sglang_own(self):
        self.refused("a vllm image for sglang", image=f"vllm/vllm-openai@{DIGEST}")
        self.refused("a vllm argument", args={"gpu-memory-utilization": 0.6})
        self.refused("an unknown algorithm", args={"speculative-algorithm": "MAGIC"})
        self.refused("a memory fraction out of range", args={"mem-fraction-static": 1.5})
        self.refused("an unknown variable", env={"LD_PRELOAD": "/x.so"})

    def test_the_draft_path_is_a_snapshot_in_the_mounted_store(self):
        # the only path argument an engine takes: exactly /hf/hub/<snapshot>, nothing outside the store
        for bad in ("/cache/evil", "/hf/hub/../../etc", DRAFT + "/../..", "/hf/hub/models--a--b/snapshots/xyz",
                    "relative/" + DRAFT, DRAFT + " --x"):
            self.refused(f"draft path {bad!r}", args={"speculative-draft-model-path": bad})


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
        # a prefix is not a whitelist (Codex): unsafe or path-moving variables are refused
        self.refused("insecure serialization", env={"VLLM_ALLOW_INSECURE_SERIALIZATION": "1"})
        self.refused("moving the cache", env={"VLLM_CACHE_ROOT": "/hf"})
        self.refused("a value out of range", env={"VLLM_PLE_MMAP": "yes"})
        self.assertEqual(spec.load(good(env={"VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1"})).env, {"VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1"})
        spec.load(good(args={"no-enable-flashinfer-autotune": True}))

    def test_unknown_top_level_keys_are_refused(self):
        with self.assertRaises(spec.SpecError):
            spec.load({**good(), "volumes": ["/:/host"]})


if __name__ == "__main__":
    unittest.main()
