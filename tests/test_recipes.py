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

    def test_components_may_not_share_an_instance(self):
        # "a.b" and "a-b" become the same instance id (Codex)
        c = recipe()["components"][0]
        self.refused("same instance id", components=[{**c, "served_name": "q.1"}, {**c, "served_name": "q-1"}],
                     agents={"default_model": "q.1"})

    def test_malformed_fields_are_refused_not_crashed_on(self):
        c = recipe()["components"][0]
        self.refused("include as a string", components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": "*.json"}}])
        self.refused("requires as a list", requires=[])
        self.refused("platforms as a string", platforms="thor-t5000")
        self.refused("title not a string", title=3)
        self.refused("components not a list", components={"a": 1})

    def test_a_draft_path_hidden_in_a_json_string_is_refused(self):
        c = recipe()["components"][0]
        self.refused("string speculative-config naming a path",
                     components=[{**c, "args": {**c["args"], "speculative-config": '{"method":"dflash","model":"/cache/x"}'}}])

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

    def test_the_bytes_parsed_are_the_bytes_verified(self):
        # From Codex's review: reading the file twice let it change between signature check and
        # parse (A, then signed B, then A again). The file is read once.
        # every read_bytes() sees the unsigned A; only the verifier's own open() sees the signed B
        evil = json.dumps(recipe(id="qwen38-27b-coder", title="evil")).encode()
        from unittest import mock
        with mock.patch.object(pathlib.Path, "read_bytes", lambda p: evil):
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
        root = put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        # without the revision manifest nothing proves the download is whole (Codex)
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        (root / "trees").mkdir()
        (root / "trees" / f"{SHA}.json").write_text(json.dumps({"files": {"config.json": {"size": 2}}}))
        st = recipes.status(r, self.hf)
        self.assertEqual(st["state"], "ready")
        self.assertEqual(st["components"][0]["snapshot"], f"models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/{SHA}")

    def test_include_lists_decide_completeness_for_partial_repos(self):
        c = recipe()["components"][0]
        r = recipes.load(recipe(components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": ["a.safetensors", "vae/*"]}}]))
        root = put(self.hf / "hub", REPO, SHA, {"a.safetensors": b"a"})
        # the revision manifest lists far more than the recipe needs: only the recipe's files count,
        # but every one of them (both vae shards, not just one match per pattern)
        (root / "trees").mkdir()
        (root / "trees" / f"{SHA}.json").write_text(json.dumps({"files": {"a.safetensors": {"size": 1},
                                                                         "vae/v1.safetensors": {"size": 1},
                                                                         "vae/v2.safetensors": {"size": 1},
                                                                         "huge.safetensors": {"size": 10**11}}}))
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", REPO, SHA, {"vae/v1.safetensors": b"v"})
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", REPO, SHA, {"vae/v2.safetensors": b"w"})
        self.assertEqual(recipes.status(r, self.hf)["state"], "ready")

    def test_specs_for_apply(self):
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        r = recipes.load(recipe())
        [s] = recipes.specs(r, self.hf, used_ports={18000})
        self.assertEqual((s.id, s.port, s.served_name), ("qwen3-8-27b", 18001, "qwen3.8-27b"))

    def tree(self, repo, sha, files):
        root = self.hf / "hub" / ("models--" + repo.replace("/", "--"))
        (root / "trees").mkdir(parents=True, exist_ok=True)
        (root / "trees" / f"{sha}.json").write_text(json.dumps({"files": {f: {"size": 2} for f in files}}))

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
        self.tree(REPO, SHA, ["config.json"])
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", "poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, {"config.json": b"{}"})
        self.tree("poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, ["config.json"])
        self.assertEqual(recipes.status(r, self.hf)["state"], "ready")
        self.assertEqual(len(recipes.fetch_commands(r)), 2)

    def test_the_draft_path_is_filled_into_the_speculative_config(self):
        r = self.draft_recipe()
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        put(self.hf / "hub", "poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        self.tree("poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, ["config.json"])
        [s] = recipes.specs(r, self.hf)
        self.assertEqual(s.args["speculative-config"], {"method": "dflash", "num_speculative_tokens": 7,
                         "model": "/hf/hub/models--poolside--Laguna-S-2.1-DFlash-NVFP4/snapshots/" + "b" * 40})

    def test_an_sglang_draft_path_is_filled_into_its_argument(self):
        c = recipe()["components"][0]
        draft = {"repo": "inclusionAI/Ling-3.0-flash-dspark", "revision": "b" * 40}
        r = recipes.load(recipe(components=[{**c, "engine": "sglang", "image": f"nvcr.io/nvidia/sglang@{DIGEST}",
                                             "draft": draft, "args": {"mem-fraction-static": 0.6,
                                                                      "speculative-algorithm": "DSPARK"}}]))
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        put(self.hf / "hub", draft["repo"], "b" * 40, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        self.tree(draft["repo"], "b" * 40, ["config.json"])
        [s] = recipes.specs(r, self.hf)
        path = "/hf/hub/models--inclusionAI--Ling-3.0-flash-dspark/snapshots/" + "b" * 40
        self.assertEqual(s.args["speculative-draft-model-path"], path)
        self.assertNotIn("speculative-config", s.args)
        self.assertEqual(recipes.expected(r, self.hf)[c["served_name"]][2]["speculative-draft-model-path"], path)

    def test_an_sglang_recipe_cannot_name_its_draft_path(self):
        c = recipe()["components"][0]
        path = "/hf/hub/models--inclusionAI--Ling-3.0-flash-dspark/snapshots/" + "b" * 40
        with self.assertRaises(recipes.RecipeError):
            recipes.load(recipe(components=[{**c, "engine": "sglang", "image": f"nvcr.io/nvidia/sglang@{DIGEST}",
                                             "args": {"speculative-draft-model-path": path}}]))

    def h3_recipe(self):
        c = recipe()["components"][0]
        h3 = {"role": "video", "served_name": "minimax-h3", "engine": "comfyui", "image": "raytone/comfyui@local",
              "model": {"repo": "Comfy-Org/MiniMax-H3", "revision": "c" * 40, "include": ["vae/*"]},
              "args": {"gpu-only": True}}
        return recipes.load(recipe(components=[c, h3]))

    def test_a_locally_built_engine_is_named_not_pinned(self):
        # its image ID differs from machine to machine: the recipe names it, the machine's own
        # engines file (scripts/build-engine) pins it
        r = self.h3_recipe()
        self.assertEqual(r.components[1].image, "raytone/comfyui@local")
        with self.assertRaises(recipes.RecipeError):
            c = recipe()["components"][0]
            recipes.load(recipe(components=[{**c, "image": "vllm/vllm-openai@local"}]))

    def test_the_local_image_resolves_from_this_machine(self):
        r = self.h3_recipe()
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        put(self.hf / "hub", "Comfy-Org/MiniMax-H3", "c" * 40, {"vae/v.safetensors": b"v"})
        self.tree("Comfy-Org/MiniMax-H3", "c" * 40, ["vae/v.safetensors", "diffusion_models/big.safetensors"])
        built = {"comfyui": {"image": "raytone/comfyui@sha256:" + "d" * 64}}
        specs = recipes.specs(r, self.hf, images=built)
        self.assertEqual(specs[1].image, "raytone/comfyui@sha256:" + "d" * 64)
        self.assertEqual(recipes.expected(r, self.hf, images=built)["minimax-h3"][0], "raytone/comfyui@sha256:" + "d" * 64)
        with self.assertRaises(recipes.RecipeError) as e:
            recipes.specs(r, self.hf, images={})
        self.assertIn("build-engine comfyui", str(e.exception))

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
