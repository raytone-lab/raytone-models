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
    # logic.js is UTF-8 and has an em dash in it; read_text() and text=True without
    # this use the console locale codec, so on a non-UTF-8 console every test in
    # this file errors before it runs anything
    src = JS.read_text(encoding="utf-8").replace(".pragma library", "")
    prog = src + f"\nprocess.stdout.write(JSON.stringify({fn}(...{json.dumps(list(args))})));"
    return json.loads(subprocess.run(["node", "-e", prog], capture_output=True, encoding="utf-8", check=True).stdout)


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
        # From Codex's review: a recipe's files verified here are ready, whatever partial blobs of
        # other variants lie in the repo
        self.assertEqual(call("modelState", {"complete": False, "progress": 0.19, "incomplete": 1, "missing": ["x"],
                                             "download": {"state": "done", "recipe": "raytone-studio"}}), "ready")

    def test_chat_models_leave_out_video_engines(self):
        inst = [{"served_name": "q", "ready": True, "chat": True}, {"served_name": "h3", "ready": True, "chat": False},
                {"served_name": "m", "ready": False, "chat": True}]
        self.assertEqual([i["served_name"] for i in call("chatModels", inst)], ["q"])

    def test_include_patterns_match_like_fnmatch(self):
        import fnmatch
        cases = [("x-Q8_0.gguf", "x-Q[8]_0.gguf"), ("x-Q8_0.gguf", "x-Q[!4]_0.gguf"), ("x-Q4_0.gguf", "x-Q[!4]_0.gguf"),
                 ("dir/x.gguf", "*.gguf"), ("x-Q8_0.gguf", "x-Q?_0.gguf"), ("a[b.gguf", "a[b.gguf"), ("x+y.gguf", "x+y.gguf"),
                 ("x-Q8_0.gguf", "x-Q[0-9]_0.gguf"), ("x].gguf", "x[]].gguf"), ("xa.gguf", "x[!]].gguf"),
                 # From Codex's review: reversed ranges are dropped, as Python does, not an error
                 ("x-Q8_0.gguf", "x-Q[!9-0]_0.gguf"), ("x-Q8_0.gguf", "x-Q[9-0]_0.gguf"), ("x-Q8_0.gguf", "x-Q[a-z8]_0.gguf"),
                 ("x-.gguf", "x[-].gguf"), ("x-.gguf", "x[a-].gguf"), ("x^.gguf", "x[^].gguf"), ("x&.gguf", "x[&&].gguf")]
        for path, pattern in cases:
            self.assertEqual(call("includeMatch", path, pattern), fnmatch.fnmatchcase(path, pattern), (path, pattern))

    def test_include_patterns_agree_with_fnmatch_on_random_patterns(self):
        import random
        from raytone_models import downloads
        rng = random.Random(7)
        alphabet = "ab9-]![*?^\\/."
        cases = [("".join(rng.choice("ab9-]^/.") for _ in range(rng.randint(0, 4))),
                  "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 6)))) for _ in range(400)]
        src = JS.read_text(encoding="utf-8").replace(".pragma library", "")
        prog = src + f"\nprocess.stdout.write(JSON.stringify({json.dumps(cases)}.map(function (c) {{" \
                     "try { return includeMatch(c[0], c[1]) } catch (e) { return 'error: ' + e.message } })));"
        got = json.loads(subprocess.run(["node", "-e", prog], capture_output=True, encoding="utf-8", check=True).stdout)
        for (path, pattern), g in zip(cases, got):
            # the reference is the downloader's own rule (fnmatch, with "dir/" meaning all below)
            self.assertEqual(g, downloads._matches(path, [pattern]), (path, pattern))

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

    def test_launch_arguments(self):
        self.assertEqual(call("launchArgs", "opencode"), ["opencode"])
        self.assertEqual(call("launchArgs", "copilot"),
                         ["--app-id=org.omarchy.copilot", "raytone-models", "agent-exec", "copilot"])
        self.assertIsNone(call("launchArgs", "gemini"))
        # OpenClaw's terminal UI attaches to its gateway, which Omarchy's launcher starts if needed
        self.assertEqual(call("launchArgs", "openclaw"), ["omarchy-launch-openclaw", "--tui"])
        # From Codex's review: Pi and Oh My Pi keep a saved default model, which may be a cloud one
        for agent in ("pi", "omp"):
            self.assertEqual(call("launchArgs", agent), [agent, "--model", "raytone/local"])

    def test_a_web_only_entry_has_no_command_to_launch(self):
        # Raytone Codesphere is opened in a browser; a null command is what keeps Launch off its card
        self.assertIsNone(call("launchArgs", "codesphere"))
        self.assertIsNone(call("agentCommand", "codesphere"))

    def test_a_name_is_shown_as_its_publisher_wrote_it(self):
        """A repo id is not a display name. Casing it by rule invents names: gpt-oss is styled
        lowercase on purpose and bge-m3 is written BGE-M3, so "no capital" says nothing about
        whether a publisher styled the name. Anything not explicitly listed is left alone."""
        for repo in ("Comfy-Org/MiniMax-H3", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead",
                     "RedHatAI/Muse-Glimmer-30B-NVFP4", "lightx2v/Minimax-h3-Turbo-SLA",
                     "inclusionAI/Ling-3.0-flash-int4", "unsloth/Qwen3-0.6B-GGUF",
                     "openai/gpt-oss-20b", "BAAI/bge-m3",
                     "stabilityai/stable-diffusion-xl-base-1.0",
                     "microsoft/Phi-3-mini-4k-instruct"):
            self.assertEqual(call("modelName", repo), repo.split("/")[1], repo)

    def test_the_one_name_that_is_listed(self):
        """Comfy-Org publishes this as z_image_turbo, and it was the only row on Local models
        reading like a filename instead of a model."""
        self.assertEqual(call("modelName", "Comfy-Org/z_image_turbo"), "Z-Image-Turbo")

    def test_a_basename_off_objects_prototype_is_not_a_name(self):
        # a bare lookup would find Object.prototype.constructor and show a function as the name
        for repo in ("org/constructor", "org/toString", "org/hasOwnProperty"):
            self.assertEqual(call("modelName", repo), repo.split("/")[1], repo)

    def test_the_served_name_is_the_same_whoever_starts_it(self):
        """The Studio trio serves this model as z-image-turbo. Run has to arrive at the same name,
        or the one model answers under two depending on how it was started."""
        self.assertEqual(call("servedName", "Comfy-Org/z_image_turbo"), "z-image-turbo")
        self.assertEqual(call("servedName", "Comfy-Org/MiniMax-H3"), "minimax-h3")
        self.assertEqual(call("servedName", "RedHatAI/Muse-Glimmer-30B-NVFP4"), "muse-glimmer-30b-nvfp4")

    def test_a_served_name_spec_py_would_refuse(self):
        """NAME_RE in spec.py is ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ -- it wants a letter or digit
        first, so a run of separators must collapse and the edges must be trimmed rather than
        becoming dashes that make start fail."""
        self.assertEqual(call("servedName", "org/a__b"), "a-b")
        self.assertEqual(call("servedName", "org/_a_"), "a")
        self.assertEqual(call("servedName", "org/--a--b--"), "a-b")
        self.assertEqual(call("servedName", "org/Qwen3-0.6B-GGUF"), "qwen3-0.6b-gguf")

    def test_agent_command(self):
        self.assertEqual(call("agentCommand", "claude"), "claude")
        self.assertEqual(call("agentCommand", "opencode"), "opencode")
        self.assertEqual(call("agentCommand", "codex"), "codex")
        self.assertEqual(call("agentCommand", "hermes"), "hermes")
        self.assertEqual(call("agentCommand", "omp"), "omp")
        self.assertEqual(call("agentCommand", "copilot"), "copilot")
        self.assertIsNone(call("agentCommand", "gemini"))


if __name__ == "__main__":
    unittest.main()
