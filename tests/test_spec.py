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


H3 = "models--Comfy-Org--MiniMax-H3/snapshots/" + "b" * 40


def comfyui(**over):
    s = good(engine="comfyui", image=f"raytone/comfyui@{DIGEST}", model=H3, served_name="minimax-h3",
             args={"gpu-only": True, "reserve-vram": 2.0}, env={})
    s.update(over)
    return s


class ComfyuiSpecTests(unittest.TestCase):
    def test_a_good_comfyui_spec_loads(self):
        self.assertEqual(spec.load(comfyui()).engine, "comfyui")

    def refused(self, why, **over):
        with self.assertRaises(spec.SpecError, msg=why):
            spec.load(comfyui(**over))

    def test_only_the_locally_built_image_and_its_own_arguments(self):
        self.refused("a registry image", image=f"yanwk/comfyui-boot@{DIGEST}")
        self.refused("a vllm argument", args={"max-model-len": 4096})
        self.refused("listen elsewhere", args={"listen": "0.0.0.0"})
        self.refused("extra paths", args={"extra-model-paths-config": "/etc/x.yaml"})
        self.refused("reserve out of range", args={"reserve-vram": 500.0})


GGUF = "models--unsloth--Qwen3-0.6B-GGUF/snapshots/" + "9" * 40


def llamacpp(**over):
    s = good(engine="llamacpp", image=f"raytone/llamacpp@{DIGEST}", model=GGUF, served_name="qwen3-0.6b",
             args={"model-file": "Qwen3-0.6B-Q4_K_M.gguf", "ctx-size": 32768, "n-gpu-layers": 999, "flash-attn": "on",
                   "jinja": True},
             env={})
    s.update(over)
    return s


class LlamacppSpecTests(unittest.TestCase):
    def test_a_good_llamacpp_spec_loads(self):
        self.assertEqual(spec.load(llamacpp()).engine, "llamacpp")
        spec.load(llamacpp(args={"model-file": "Q8_0/x-Q8_0-00001-of-00002.gguf", "mmproj-file": "mmproj-F16.gguf"}))

    def refused(self, why, **over):
        with self.assertRaises(spec.SpecError, msg=why):
            spec.load(llamacpp(**over))

    def test_the_gguf_files_stay_inside_the_snapshot(self):
        for bad in ("../../x.gguf", "/etc/passwd.gguf", "a/../../b.gguf", "x.bin", "", "-m.gguf", "x.gguf --lora y"):
            self.refused(f"model-file {bad!r}", args={"model-file": bad})
            self.refused(f"mmproj-file {bad!r}", args={"model-file": "a.gguf", "mmproj-file": bad})

    def test_a_trailing_newline_is_not_a_match(self):
        # From Codex's review of PR #7: "$" also matches before a final newline
        self.refused("model-file", args={"model-file": "a.gguf\n"})

    def test_a_model_file_is_required(self):
        self.refused("no model-file", args={"ctx-size": 4096})

    def test_only_its_own_arguments(self):
        self.refused("a registry image", image=f"ghcr.io/ggml-org/llama.cpp@{DIGEST}")
        self.refused("a vllm argument", args={"model-file": "a.gguf", "max-model-len": 4096})
        self.refused("a bad cache type", args={"model-file": "a.gguf", "cache-type-k": "evil"})


class LocalVllmTests(unittest.TestCase):
    """A vLLM image built on this machine (raytone/vllm-NAME), e.g. with a model's own patches that
    are not ours to ship, and the arguments Qwen3.8 Flash Next's single-device lane needs."""

    def flashnext(self, **over):
        d = self._flashnext()
        d.update(over)
        return d

    def _flashnext(self):
        return good(image=f"raytone/vllm-flashnext@{DIGEST}", memory_gib=99,
                    args={"gpu-memory-utilization": 0.773, "kv-cache-dtype": "fp8", "mamba-ssm-cache-dtype": "bfloat16",
                          "load-format": "safetensors", "safetensors-load-strategy": "lazy", "enable-chunked-prefill": True,
                          "enable-prompt-tokens-details": True, "distributed-executor-backend": "mp",
                          "engram-config": {"cpu_offload": True}, "kv-cache-memory-bytes": "12G",
                          "compilation-config": {"mode": 0, "cudagraph_mode": "FULL_DECODE_ONLY"}},
                    env={"VLLM_PLE_MMAP_DIR": "/cache/vllm/ple_mmap_v030", "VLLM_PLE_MMAP_ADVICE": "1",
                         "VLLM_MTP_DRAFT_VOCAB": "/opt/raytone/draft_vocab.txt", "VLLM_USE_V2_MODEL_RUNNER": "1",
                         "VLLM_FLASHINFER_AUTOTUNE_CACHE_DIR": "/cache/fi_autotune", "MAX_JOBS": "2",
                         "FLASHINFER_NVCC_THREADS": "1"})

    def test_a_local_vllm_image_with_its_lane_loads(self):
        s = spec.load(self.flashnext())
        self.assertEqual((s.memory_gib, spec.is_local(s.image)), (99, True))
        self.assertFalse(spec.is_local(f"vllm/vllm-openai@{DIGEST}"))

    def test_bounds(self):
        for over in ({"image": f"raytone/comfyui@{DIGEST}"}, {"image": f"raytone/vllm-@{DIGEST}"},
                     {"memory_gib": 500}, {"memory_gib": True},
                     {"env": {"VLLM_PLE_MMAP_DIR": "/root/.ssh"}}, {"env": {"VLLM_PLE_MMAP_DIR": "/cache/../etc"}},
                     {"env": {"VLLM_MTP_DRAFT_VOCAB": "/etc/shadow"}}, {"args": {"kv-cache-memory-bytes": "12G --x"}},
                     {"args": {"distributed-executor-backend": "ray"}}):
            with self.subTest(over=over), self.assertRaises(spec.SpecError):
                spec.load(self.flashnext(**over))

    def test_json_arguments_have_a_schema(self):
        # From Codex's review of PR #13: vLLM reads paths and importable names from these objects
        base = self._flashnext()["args"]
        for key, bad in (("compilation-config", {"mode": 1, "backend": "os.system"}),
                         ("compilation-config", {"cache_dir": "/tmp/x"}),
                         ("compilation-config", {"mode": "0"}),
                         ("engram-config", {"cpu_offload": True, "path": "/x"}),
                         ("speculative-config", {"method": "mtp", "model": "/cache/evil"}),
                         ("speculative-config", {"method": "mtp", "num_speculative_tokens": 3, "draft_model_config": {}}),
                         ("limit-mm-per-prompt", {"image": "all"})):
            with self.subTest(key=key, bad=bad), self.assertRaises(spec.SpecError):
                spec.load(self.flashnext(args={**base, key: bad}))
        ok = {"method": "mtp", "num_speculative_tokens": 3, "use_local_argmax_reduction": True,
              "disable_eagle_block_drop": True, "index_share_for_mtp_iteration": True}
        spec.load(self.flashnext(args={**base, "speculative-config": ok}))
        spec.load(good(args={"speculative-config": {"method": "dflash", "num_speculative_tokens": 7,
                                                    "model": "/hf/hub/models--a--b/snapshots/" + "c" * 40}}))
        spec.load(good(args={"speculative-config": '{"method":"mtp","num_speculative_tokens":3}'}))
        spec.load(good(args={"limit-mm-per-prompt": {"image": 2, "video": 0}}))

    def test_memory_is_optional(self):
        self.assertIsNone(spec.load(good()).memory_gib)


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
        for field, value in (("id", "qwen\n"), ("served_name", "q\n"), ("model", SNAPSHOT + "\n"),
                             ("image", f"vllm/vllm-openai@{DIGEST}\n")):
            self.refused(f"{field} with a trailing newline", **{field: value})
        self.refused("a word argument with a trailing newline", args={"tool-call-parser": "qwen3\n"})
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
