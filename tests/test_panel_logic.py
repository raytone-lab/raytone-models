"""The panel's pure logic (plugin/raytone.models/ModelsLogic.js), run under node when it is there."""
import json
import pathlib
import shutil
import subprocess
import unittest

JS = pathlib.Path(__file__).resolve().parents[1] / "plugin" / "raytone.models" / "ModelsLogic.js"


def call(fn, *args):
    # ModelsLogic.js is a QML JavaScript resource (.pragma library): plain functions, no exports.
    src = JS.read_text().replace(".pragma library", "")
    prog = src + f"\nprocess.stdout.write(JSON.stringify({fn}(...{json.dumps(list(args))})));"
    return json.loads(subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True).stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PanelLogicTests(unittest.TestCase):
    def test_run_argv_for_a_qwen_model_has_its_parsers(self):
        argv = call("runArgv", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", "009632fef96d" + "0" * 28)
        # the row's revision, so two revisions of one repo can each be started (Codex)
        self.assertEqual(argv[:4], ["raytone-models", "start",
                                    "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead@009632fef96d" + "0" * 28, "--engine"])
        self.assertIn("tool-call-parser=qwen3_coder", argv)
        self.assertIn("reasoning-parser=qwen3", argv)
        self.assertEqual(argv[argv.index("--name") + 1], "qwen3.8-27b-nvfp4-bf16-lmhead")

    def test_run_argv_for_other_models_has_no_guessed_parsers(self):
        argv = call("runArgv", "RedHatAI/Muse-Glimmer-30B-NVFP4", "e" * 40)
        self.assertFalse([a for a in argv if "parser" in a])
        self.assertIn("gpu-memory-utilization=0.6", argv)

    def test_recipe_button_does_the_next_useful_thing(self):
        r = {"id": "qwen38-27b-coder", "state": "missing", "running": False}
        self.assertEqual(call("recipeArgv", r)[2:4], ["fetch", "qwen38-27b-coder"])
        self.assertEqual(call("recipeAction", r, False), "Download")
        r["state"] = "ready"
        self.assertEqual(call("recipeArgv", r)[2], "apply")
        r["running"] = True
        self.assertEqual(call("recipeArgv", r)[2], "stop")
        self.assertEqual(call("recipeAction", r, True), "Stopping…")

    def test_recipe_detail(self):
        r = {"components": [{"served_name": "qwen3.8-27b"}, {"served_name": "minimax-h3"}], "memory_gib": 100, "disk_gib": 60}
        self.assertEqual(call("recipeDetail", r), "qwen3.8-27b + minimax-h3 · needs 100 GiB memory, 60 GiB disk")

    def test_sizes(self):
        self.assertEqual(call("gib", 23770000000), "22.1 GiB")
        self.assertEqual(call("gib", 0), "0 GiB")

    def test_model_state(self):
        self.assertEqual(call("modelState", {"complete": True, "incomplete": 0}), "ready")
        self.assertEqual(call("modelState", {"complete": False, "progress": 0.25, "incomplete": 1}), "downloading 25%")
        self.assertEqual(call("modelState", {"complete": None, "incomplete": 0, "missing": []}), "ready")

    def test_runnable_formats(self):
        self.assertTrue(call("runnable", {"format": "safetensors", "complete": True}))
        self.assertFalse(call("runnable", {"format": "diffusion", "complete": True}))
        self.assertFalse(call("runnable", {"format": "safetensors", "complete": False}))


if __name__ == "__main__":
    unittest.main()
