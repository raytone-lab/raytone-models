"""Recipes: Raytone AI Lab's tested combinations of models, engines and parameters. A recipe is
applied only when its signature verifies; its components go through the same spec checks as any
instance, and its models must be in the store at the pinned revision."""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from raytone_models import recipes
from tests.test_spec import DIGEST
from tests.test_store import SHA, put

REPO = "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead"


def recipe(**over):
    r = {
        "schema": 1,
        "id": "qwen38-27b-coder",
        "title": "Qwen3.8 27B NVFP4 for coding agents",
        "description": "Dense 27B, NVFP4, MTP speculative decoding, 256K context.",
        "platforms": ["thor-t5000"],
        "requires": {"memory_gib": 60, "disk_gib": 30},
        "source": "Parameters from Mia's AI Lab single-Spark recipe, adapted to vLLM on the Thor",
        "components": [{
            "role": "chat",
            "served_name": "qwen3.8-27b",
            "model": {"repo": REPO, "revision": SHA},
            "engine": "vllm",
            "image": f"vllm/vllm-openai@{DIGEST}",
            "args": {"gpu-memory-utilization": 0.6, "max-model-len": 262144, "enable-prefix-caching": True},
            "env": {},
        }],
        "agents": {"default_model": "qwen3.8-27b"},
    }
    r.update(over)
    return r


class SchemaTests(unittest.TestCase):
    def test_a_good_recipe_loads(self):
        r = recipes.load(recipe())
        self.assertEqual((r.id, len(r.components)), ("qwen38-27b-coder", 1))

    def refused(self, why, **over):
        with self.assertRaises(recipes.RecipeError, msg=why):
            recipes.load(recipe(**over))

    def test_refusals(self):
        c = recipe()["components"][0]
        self.refused("unknown schema", schema=2)
        self.refused("bad id", id="Qwen 27B")
        self.refused("no components", components=[])
        self.refused("a revision that is a branch", components=[{**c, "model": {"repo": REPO, "revision": "main"}}])
        self.refused("an argument the engine does not take", components=[{**c, "args": {"load-format": "pt"}}])
        self.refused("an image that is not pinned", components=[{**c, "image": "vllm/vllm-openai:latest"}])
        self.refused("two components with one name", components=[c, c])
        self.refused("an unknown top-level field", extra=1)
        self.refused("an include pattern leaving the repo", components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": ["../x"]}}])

    def test_the_default_model_must_be_a_component(self):
        self.refused("default not served", agents={"default_model": "gpt-5"})


class SignatureTests(unittest.TestCase):
    """ssh-keygen -Y: offline, no extra dependency, on every Omarchy and macOS."""

    def setUp(self):
        if not shutil.which("ssh-keygen"):
            self.skipTest("no ssh-keygen")
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(t / "key")], check=True)
        pub = (t / "key.pub").read_text().split()
        (t / "allowed").write_text(f"{recipes.SIGNER} {pub[0]} {pub[1]}\n")
        self.t = t
        self.file = t / "qwen38-27b-coder.json"
        self.file.write_text(json.dumps(recipe()))
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(t / "key"), "-n", recipes.NAMESPACE, str(self.file)],
                       check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_signed_recipe_verifies(self):
        r = recipes.read(self.file, allowed_signers=self.t / "allowed")
        self.assertEqual(r.id, "qwen38-27b-coder")

    def test_a_changed_recipe_does_not(self):
        d = recipe()
        d["components"][0]["args"]["gpu-memory-utilization"] = 0.95
        self.file.write_text(json.dumps(d))
        with self.assertRaises(recipes.RecipeError):
            recipes.read(self.file, allowed_signers=self.t / "allowed")

    def test_an_unsigned_recipe_does_not(self):
        pathlib.Path(str(self.file) + ".sig").unlink()
        with self.assertRaises(recipes.RecipeError):
            recipes.read(self.file, allowed_signers=self.t / "allowed")


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hf = pathlib.Path(self.tmp.name) / "hf"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_until_the_pinned_revision_is_here(self):
        r = recipes.load(recipe())
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", REPO, "1" * 40, {"config.json": b"{}"})          # another revision
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        st = recipes.status(r, self.hf)
        self.assertEqual(st["state"], "ready")
        self.assertEqual(st["components"][0]["snapshot"], f"models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/{SHA}")

    def test_include_lists_decide_completeness_for_partial_repos(self):
        c = recipe()["components"][0]
        r = recipes.load(recipe(components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": ["a.safetensors", "vae/*"]}}]))
        root = put(self.hf / "hub", REPO, SHA, {"a.safetensors": b"a"})
        # the revision manifest lists far more than the recipe needs: only the recipe's files count
        (root / "trees").mkdir()
        (root / "trees" / f"{SHA}.json").write_text(json.dumps({"files": {"a.safetensors": {"size": 1},
                                                                         "vae/v.safetensors": {"size": 1},
                                                                         "huge.safetensors": {"size": 10**11}}}))
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", REPO, SHA, {"vae/v.safetensors": b"v"})
        self.assertEqual(recipes.status(r, self.hf)["state"], "ready")

    def test_specs_for_apply(self):
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        r = recipes.load(recipe())
        [s] = recipes.specs(r, self.hf, used_ports={18000})
        self.assertEqual((s.id, s.port, s.served_name), ("qwen3-8-27b", 18001, "qwen3.8-27b"))

    def draft_recipe(self):
        c = recipe()["components"][0]
        draft = {"repo": "poolside/Laguna-S-2.1-DFlash-NVFP4", "revision": "b" * 40}
        return recipes.load(recipe(components=[{**c, "draft": draft,
                                                "args": {**c["args"], "speculative-config": {"method": "dflash", "num_speculative_tokens": 7}}}]))

    def test_a_draft_model_is_part_of_the_recipe(self):
        # DFlash and other speculative decoders load a second repo: it is pinned and fetched too,
        # and the recipe is ready only when both are here
        r = self.draft_recipe()
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", "poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, {"config.json": b"{}"})
        self.assertEqual(recipes.status(r, self.hf)["state"], "ready")
        self.assertEqual(len(recipes.fetch_commands(r)), 2)

    def test_the_draft_path_is_filled_into_the_speculative_config(self):
        r = self.draft_recipe()
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        put(self.hf / "hub", "poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, {"config.json": b"{}"})
        [s] = recipes.specs(r, self.hf)
        self.assertEqual(s.args["speculative-config"], {"method": "dflash", "num_speculative_tokens": 7,
                         "model": "/hf/hub/models--poolside--Laguna-S-2.1-DFlash-NVFP4/snapshots/" + "b" * 40})

    def test_a_recipe_cannot_name_its_own_draft_path(self):
        c = recipe()["components"][0]
        with self.assertRaises(recipes.RecipeError):
            recipes.load(recipe(components=[{**c, "args": {**c["args"],
                         "speculative-config": {"method": "dflash", "model": "/cache/../etc"}}}]))

    def test_fetch_commands_pin_the_revision(self):
        c = recipe()["components"][0]
        r = recipes.load(recipe(components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": ["a/*"]}}]))
        [cmd] = recipes.fetch_commands(r)
        self.assertEqual(cmd, ["hf", "download", REPO, "--revision", SHA, "--include", "a/*"])


if __name__ == "__main__":
    unittest.main()
