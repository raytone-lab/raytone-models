"""The model store is a Hugging Face cache (HF_HOME/hub): what is there, how big, in which format."""
import json
import os
import pathlib
import tempfile
import unittest

from raytone_models import store

SHA = "009632fef96dd349150baa780c984e62e70e91fe"


def put(hub, repo, sha, files, incomplete=()):
    """Lay out one snapshot the way huggingface_hub does: content in blobs/, links in snapshots/."""
    root = hub / ("models--" + repo.replace("/", "--"))
    (root / "blobs").mkdir(parents=True, exist_ok=True)
    (root / "refs").mkdir(exist_ok=True)
    (root / "refs" / "main").write_text(sha)
    for path, content in files.items():
        blob = root / "blobs" / f"b{abs(hash(content)) % 10**12}"
        blob.write_bytes(content)
        link = root / "snapshots" / sha / path
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(os.path.relpath(blob, link.parent))
    for name in incomplete:
        (root / "blobs" / f"{name}.incomplete").write_bytes(b"x" * 10)
    return root


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name)
        self.hub = self.home / "hub"

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_store(self):
        self.assertEqual(store.list_models(self.home), [])

    def test_a_safetensors_snapshot(self):
        cfg = json.dumps({"quantization_config": {"quant_method": "modelopt", "quant_algo": "NVFP4"}}).encode()
        put(self.hub, "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", SHA,
            {"config.json": cfg, "model-00001-of-00002.safetensors": b"a" * 100,
             "model-00002-of-00002.safetensors": b"b" * 50, "tokenizer.json": b"{}"})
        [m] = store.list_models(self.home)
        self.assertEqual(m.repo, "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead")
        self.assertEqual(m.revision, SHA)
        self.assertEqual(m.snapshot, f"models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/{SHA}")
        self.assertEqual(m.format, "safetensors")
        self.assertEqual(m.quant, "NVFP4")
        self.assertEqual(m.size, 100 + 50 + 2 + len(cfg))
        self.assertEqual(m.incomplete, 0)

    def test_shared_blobs_count_once(self):
        put(self.hub, "a/b", SHA, {"x.safetensors": b"same", "copy/x.safetensors": b"same"})
        [m] = store.list_models(self.home)
        self.assertEqual(m.size, 4)

    def test_formats(self):
        put(self.hub, "u/g", SHA, {"m-Q4_K_M.gguf": b"g"})
        put(self.hub, "c/v", SHA, {"diffusion_models/h3.safetensors": b"d", "text_encoders/t.safetensors": b"t"})
        got = {m.repo: m.format for m in store.list_models(self.home)}
        self.assertEqual(got, {"u/g": "gguf", "c/v": "diffusion"})

    def test_quant_from_hf_quant_config(self):
        q = json.dumps({"quantization": {"quant_algo": "NVFP4"}}).encode()
        put(self.hub, "n/m", SHA, {"hf_quant_config.json": q, "model.safetensors": b"w"})
        self.assertEqual(store.list_models(self.home)[0].quant, "NVFP4")

    def test_downloads_in_progress_are_reported(self):
        put(self.hub, "a/b", SHA, {"x.safetensors": b"w"}, incomplete=("c1", "c2"))
        self.assertEqual(store.list_models(self.home)[0].incomplete, 2)

    def test_a_broken_link_is_not_counted(self):
        root = put(self.hub, "a/b", SHA, {"x.safetensors": b"w"})
        (root / "snapshots" / SHA / "gone.safetensors").symlink_to("../../blobs/missing")
        [m] = store.list_models(self.home)
        self.assertEqual(m.size, 1)
        self.assertEqual(m.missing, ["gone.safetensors"])


if __name__ == "__main__":
    unittest.main()
