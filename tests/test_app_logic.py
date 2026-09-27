"""The app's pure logic (app/logic.js): formatting, memory fit, recommended variant, recipe action,
tokens per second. Run under node when it is installed."""
import json
import pathlib
import shutil
import subprocess
import unittest

JS = pathlib.Path(__file__).resolve().parents[1] / "app" / "logic.js"
GIB = 1 << 30
TOTAL = 122 * GIB


def call(fn, *args):
    src = JS.read_text().replace(".pragma library", "")
    prog = src + f"\nprocess.stdout.write(JSON.stringify({fn}(...{json.dumps(list(args))})));"
    return json.loads(subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True).stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AppLogicTests(unittest.TestCase):
    def test_gib(self):
        self.assertEqual(call("gib", 23770000000), "22.14 GiB")
        self.assertEqual(call("gib", 0), "0 GiB")
        self.assertEqual(call("gib", None), "—")

    def test_fit_against_the_unified_pool(self):
        self.assertEqual(call("fit", 20 * GIB, TOTAL), "fits")
        self.assertEqual(call("fit", 95 * GIB, TOTAL), "tight")
        self.assertEqual(call("fit", 110 * GIB, TOTAL), "too large")
        self.assertEqual(call("fit", 20 * GIB, 0), "unknown")

    def test_recommended_variant(self):
        v = [{"name": "BF16", "size": 53 * GIB}, {"name": "Q4_K_M", "size": 17 * GIB},
             {"name": "Q8_0", "size": 29 * GIB}, {"name": "UD-IQ1_S", "size": 7 * GIB}]
        self.assertEqual(call("recommended", v, TOTAL), "Q4_K_M")
        self.assertEqual(call("recommended", [x for x in v if x["name"] != "Q4_K_M"], TOTAL), "Q8_0")
        self.assertEqual(call("recommended", [{"name": "all files", "size": 200 * GIB}], TOTAL), "")

    def test_recipe_action(self):
        self.assertEqual(call("recipeAction", {"state": "missing", "running": False, "conflicts": []}), "download")
        self.assertEqual(call("recipeAction", {"state": "ready", "running": False, "conflicts": []}), "apply")
        self.assertEqual(call("recipeAction", {"state": "ready", "running": True, "conflicts": []}), "stop")
        self.assertEqual(call("recipeAction", {"state": "ready", "running": False, "conflicts": ["q"]}), "conflict")

    def test_tokens_per_second_from_two_samples(self):
        a = {"time": 100.0, "instances": [{"id": "q", "counters": {"generation_tokens": 1000}}]}
        b = {"time": 102.0, "instances": [{"id": "q", "counters": {"generation_tokens": 1050}}]}
        self.assertEqual(call("tokensPerSecond", a, b, "q"), 25)
        self.assertIsNone(call("tokensPerSecond", None, b, "q"))
        c = {"time": 104.0, "instances": [{"id": "q", "counters": None}]}
        self.assertIsNone(call("tokensPerSecond", b, c, "q"))

    def test_short_revision_and_repo_parts(self):
        self.assertEqual(call("shortRev", "009632fef96dd349150baa780c984e62e70e91fe"), "009632fe")
        self.assertEqual(call("repoName", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead"), "Qwen3.8-27B-NVFP4-BF16-LMHead")
        self.assertEqual(call("repoOrg", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead"), "RadixArk")

    def test_model_state(self):
        self.assertEqual(call("modelState", {"complete": True, "incomplete": 0, "missing": []}), "ready")
        self.assertEqual(call("modelState", {"complete": False, "progress": 0.362, "incomplete": 0, "missing": ["a"]}),
                         "incomplete 36%")
        self.assertEqual(call("modelState", {"complete": None, "incomplete": 0, "missing": []}), "unverified")
        # partial blobs left by an interrupted earlier attempt do not make a complete model unready
        self.assertEqual(call("modelState", {"complete": True, "incomplete": 8, "missing": []}), "ready")
        # the variant that was downloaded is what counts, not the whole repo
        self.assertEqual(call("modelState", {"complete": False, "progress": 0.03, "incomplete": 0, "missing": ["x"],
                                             "download": {"state": "done"}}), "ready")
        self.assertEqual(call("modelState", {"complete": False, "progress": 0.03, "incomplete": 1, "missing": ["x"],
                                             "download": {"state": "running", "progress": 0.4}}), "downloading 40%")

    def test_chat_models_leave_out_video_engines(self):
        inst = [{"served_name": "q", "ready": True, "chat": True}, {"served_name": "h3", "ready": True, "chat": False},
                {"served_name": "m", "ready": False, "chat": True}]
        self.assertEqual([i["served_name"] for i in call("chatModels", inst)], ["q"])

    def test_gguf_files_to_run(self):
        m = {"files": ["README.md", "Qwen3-0.6B-Q4_K_M.gguf", "mmproj-F16.gguf"]}
        self.assertEqual(call("ggufFiles", m), {"model": "Qwen3-0.6B-Q4_K_M.gguf", "mmproj": "mmproj-F16.gguf"})
        # a split model starts at its first part
        m = {"files": ["Q8_0/x-Q8_0-00002-of-00002.gguf", "Q8_0/x-Q8_0-00001-of-00002.gguf"]}
        self.assertEqual(call("ggufFiles", m), {"model": "Q8_0/x-Q8_0-00001-of-00002.gguf", "mmproj": None})
        # the variant that was downloaded wins over others in the same snapshot
        m = {"files": ["x-Q8_0.gguf", "x-Q4_K_M.gguf"], "download": {"state": "done", "include": ["x-Q8_0.gguf"]}}
        self.assertEqual(call("ggufFiles", m)["model"], "x-Q8_0.gguf")
        # otherwise the usual 4-bit one
        self.assertEqual(call("ggufFiles", {"files": ["x-Q8_0.gguf", "x-Q4_K_M.gguf"]})["model"], "x-Q4_K_M.gguf")
        self.assertIsNone(call("ggufFiles", {"files": ["model.safetensors"]}))
        # From Codex's review of PR #7: include patterns match like the downloader's (* crosses
        # directories), and the projector is chosen on its own
        m = {"files": ["x-Q4_K_M.gguf", "x-Q8_0.gguf", "mmproj-F16.gguf"],
             "download": {"state": "done", "include": ["*Q8_0*", "mmproj-F16.gguf"]}}
        self.assertEqual(call("ggufFiles", m), {"model": "x-Q8_0.gguf", "mmproj": "mmproj-F16.gguf"})
        m = {"files": ["x-Q8_0.gguf", "mmproj-F16.gguf"], "download": {"state": "done", "include": ["x-Q8_0.gguf"]}}
        self.assertEqual(call("ggufFiles", m), {"model": "x-Q8_0.gguf", "mmproj": "mmproj-F16.gguf"})
        m = {"files": ["Q8_0/a-Q8_0-00001-of-00002.gguf", "Q8_0/a-Q8_0-00002-of-00002.gguf", "a-Q4_K_M.gguf"],
             "download": {"state": "done", "include": ["Q8_0/"]}}
        self.assertEqual(call("ggufFiles", m)["model"], "Q8_0/a-Q8_0-00001-of-00002.gguf")

    def test_clock(self):
        self.assertEqual(call("clock", 0), "0:00")
        self.assertEqual(call("clock", 83.6), "1:23")
        self.assertEqual(call("clock", 3725), "62:05")

    def test_agent_command(self):
        self.assertEqual(call("agentCommand", "claude"), "claude")
        self.assertEqual(call("agentCommand", "opencode"), "opencode")
        self.assertIsNone(call("agentCommand", "gemini"))


if __name__ == "__main__":
    unittest.main()
