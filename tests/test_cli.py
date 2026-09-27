"""The user-facing CLI the panel calls: every command can answer in JSON; starting and stopping go
through the privileged helper with the spec on stdin."""
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

from raytone_models import cli
from tests.test_store import SHA, put

DIGEST = "sha256:" + "c" * 64


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.hf, self.reg = t / "hf", t / "reg"
        self.reg.mkdir()
        root = put(self.hf / "hub", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", SHA, {"config.json": b"{}", "m.safetensors": b"w"})
        (root / "trees").mkdir()
        (root / "trees" / f"{SHA}.json").write_text(json.dumps({"files": {"config.json": {"size": 2}, "m.safetensors": {"size": 1}}}))
        self.helper_calls = []
        self.env = cli.Env(hf_home=self.hf, registry=self.reg, state=t / "state", home=t / "home",
                           engines={"vllm": {"image": f"vllm/vllm-openai@{DIGEST}"}},
                           helper=lambda args, stdin=None: self.helper_calls.append((args, stdin)) or {"ok": True},
                           probe=lambda url: url.endswith(":18000/v1/models"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cli.main(list(argv), env=self.env)
        return rc, out.getvalue()

    def test_models_json(self):
        rc, out = self.run_cli("models", "--json")
        self.assertEqual(rc, 0)
        [m] = json.loads(out)
        self.assertEqual(m["repo"], "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead")

    def test_start_sends_a_full_spec_to_the_helper(self):
        rc, out = self.run_cli("start", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", "--engine", "vllm",
                               "--name", "qwen3.8-27b", "--arg", "gpu-memory-utilization=0.6",
                               "--arg", "max-model-len=131072", "--arg", "enable-prefix-caching", "--json")
        self.assertEqual(rc, 0, out)
        [(args, stdin)] = self.helper_calls
        self.assertEqual(args, ["start"])
        s = json.loads(stdin)
        self.assertEqual(s["model"], f"models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/{SHA}")
        self.assertEqual(s["image"], f"vllm/vllm-openai@{DIGEST}")
        self.assertEqual(s["args"], {"gpu-memory-utilization": 0.6, "max-model-len": 131072, "enable-prefix-caching": True})
        self.assertEqual((s["id"], s["port"]), ("qwen3-8-27b", 18000))

    def test_start_picks_a_free_port(self):
        (self.reg / "a.json").write_text(json.dumps({"id": "a", "served_name": "a", "port": 18000}))
        self.run_cli("start", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", "--engine", "vllm", "--name", "q")
        self.assertEqual(json.loads(self.helper_calls[0][1])["port"], 18001)

    def test_start_refuses_what_the_helper_would_refuse(self):
        rc, _ = self.run_cli("start", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", "--engine", "vllm",
                             "--name", "q", "--arg", "load-format=pt")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.helper_calls, [])

    def test_start_with_another_pinned_image(self):
        other = "vllm/vllm-openai@sha256:" + "e" * 64
        rc, _ = self.run_cli("start", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", "--engine", "vllm", "--name", "q", "--image", other)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(self.helper_calls[0][1])["image"], other)
        self.helper_calls.clear()
        rc, _ = self.run_cli("start", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", "--engine", "vllm", "--name", "q",
                             "--image", "vllm/vllm-openai:latest")
        self.assertNotEqual(rc, 0)            # a tag is not a pin: the spec refuses it
        self.assertEqual(self.helper_calls, [])

    def test_a_model_not_in_the_store_is_refused(self):
        rc, _ = self.run_cli("start", "nobody/nothing", "--engine", "vllm", "--name", "q")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.helper_calls, [])

    def test_instances_report_readiness(self):
        (self.reg / "qwen.json").write_text(json.dumps(
            {"id": "qwen", "served_name": "qwen3.8-27b", "port": 18000, "engine": "vllm", "args": {"max-model-len": 131072}}))
        (self.reg / "muse.json").write_text(json.dumps({"id": "muse", "served_name": "muse", "port": 18001, "engine": "vllm"}))
        rc, out = self.run_cli("instances", "--json")
        got = {i["served_name"]: i["ready"] for i in json.loads(out)}
        self.assertEqual(got, {"qwen3.8-27b": True, "muse": False})

    def test_a_video_engine_is_ready_by_its_own_health_check(self):
        (self.reg / "h3.json").write_text(json.dumps({"id": "h3", "served_name": "minimax-h3", "port": 18002, "engine": "comfyui"}))
        self.env.probe = lambda url: url == "http://127.0.0.1:18002/system_stats"
        rc, out = self.run_cli("instances", "--json")
        [i] = json.loads(out)
        self.assertEqual((i["served_name"], i["engine"], i["ready"]), ("minimax-h3", "comfyui", True))

    def test_locally_built_engine_images_come_from_etc(self):
        # scripts/build-engine records the image ID it built in /etc/raytone-models/engines.json
        t = pathlib.Path(self.tmp.name)
        shipped, local = t / "shipped.json", t / "local.json"
        shipped.write_text(json.dumps({"vllm": {"image": "v@x"}, "comfyui": {"note": "built locally"}}))
        local.write_text(json.dumps({"comfyui": {"image": "raytone/comfyui@sha256:" + "c" * 64, "tag": "v0.37.0"}}))
        got = cli._engines((shipped, local, t / "missing.json"))
        self.assertEqual(got["vllm"]["image"], "v@x")
        self.assertEqual(got["comfyui"], {"note": "built locally", "image": "raytone/comfyui@sha256:" + "c" * 64, "tag": "v0.37.0"})

    def test_video_runs_on_the_comfyui_instance(self):
        from tests.test_video import FakeComfy
        fake = FakeComfy()
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        (self.reg / "h3.json").write_text(json.dumps({"id": "minimax-h3", "served_name": "minimax-h3",
                                                     "port": fake.server_address[1], "engine": "comfyui"}))
        self.env.videos_dir = pathlib.Path(self.tmp.name) / "Videos"
        self.env.video_poll = 0.01
        rc, out = self.run_cli("video", "--prompt", "a red fox in snow", "--seconds", "3", "--size", "480p", "--seed", "5")
        self.assertEqual(rc, 0, out)
        lines = [json.loads(l) for l in out.splitlines()]
        self.assertTrue(pathlib.Path(lines[-1]["done"]).exists())
        wf = fake.prompts[0]["prompt"]
        h3 = next(n for n in wf.values() if n["class_type"] == "MiniMaxH3ImageToVideo")
        self.assertEqual((h3["inputs"]["length"], h3["inputs"]["width"]), (73, 864))

    def test_video_without_a_video_engine_running(self):
        rc, out = self.run_cli("video", "--prompt", "a fox")
        self.assertNotEqual(rc, 0)
        self.assertIn("error", json.loads(out.splitlines()[-1]))

    def test_stop_goes_through_the_helper(self):
        self.run_cli("stop", "qwen")
        self.assertEqual(self.helper_calls, [(["stop", "qwen"], None)])

    def test_agent_connect_uses_the_ready_models(self):
        (self.reg / "qwen.json").write_text(json.dumps(
            {"id": "qwen", "served_name": "qwen3.8-27b", "port": 18000, "engine": "vllm", "args": {"max-model-len": 131072}}))
        rc, out = self.run_cli("agent", "connect", "opencode", "--json")
        self.assertEqual(rc, 0, out)
        cfg = json.loads((self.env.home / ".config/opencode/opencode.json").read_text())
        self.assertEqual(cfg["model"], "raytone/qwen3.8-27b")
        self.assertEqual(cfg["provider"]["raytone"]["models"]["qwen3.8-27b"]["limit"]["context"], 131072)
        rc, _ = self.run_cli("agent", "revert", "opencode")
        self.assertFalse((self.env.home / ".config/opencode/opencode.json").exists())

    def test_agent_connect_needs_a_ready_model(self):
        rc, _ = self.run_cli("agent", "connect", "opencode")
        self.assertNotEqual(rc, 0)

    def test_elevation_is_pkexec_unless_told_otherwise(self):
        self.assertEqual(cli.elevate_argv({}), ["pkexec", cli.HELPER])
        self.assertEqual(cli.elevate_argv({"RAYTONE_MODELS_ELEVATE": "sudo"}), ["sudo", "-n", cli.HELPER])
        with self.assertRaises(SystemExit):
            cli.elevate_argv({"RAYTONE_MODELS_ELEVATE": "sh -c"})

    def signed_recipe(self):
        import shutil, subprocess
        from tests.test_recipes import recipe
        if not shutil.which("ssh-keygen"):
            self.skipTest("no ssh-keygen")
        t = pathlib.Path(self.tmp.name)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(t / "k")], check=True)
        pub = (t / "k.pub").read_text().split()
        (t / "allowed").write_text(f"recipes@raytone.ai {pub[0]} {pub[1]}\n")
        d = t / "recipes"
        d.mkdir()
        c = recipe()["components"][0]
        data = recipe(components=[{**c, "image": f"vllm/vllm-openai@{DIGEST}"}])
        (d / "qwen38-27b-coder.json").write_text(json.dumps(data))
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(t / "k"), "-n", "raytone-recipe",
                        str(d / "qwen38-27b-coder.json")], check=True, capture_output=True)
        (d / "tampered.json").write_text(json.dumps({**data, "id": "tampered"}))
        self.env.recipe_dirs = [d]
        self.env.allowed_signers = t / "allowed"

    def test_recipes_json_lists_signed_recipes_with_their_state(self):
        self.signed_recipe()
        rc, out = self.run_cli("recipes", "--json")
        self.assertEqual(rc, 0, out)
        got = json.loads(out)
        [r] = got["recipes"]
        self.assertEqual((r["id"], r["state"], r["running"]), ("qwen38-27b-coder", "ready", False))
        self.assertEqual([b["file"].rsplit("/", 1)[-1] for b in got["refused"]], ["tampered.json"])

    def test_recipe_apply_starts_each_component_through_the_helper(self):
        self.signed_recipe()
        rc, out = self.run_cli("recipe", "apply", "qwen38-27b-coder", "--json")
        self.assertEqual(rc, 0, out)
        [(args, stdin)] = self.helper_calls
        self.assertEqual(args, ["start"])
        s = json.loads(stdin)
        self.assertEqual((s["id"], s["served_name"], s["port"]), ("qwen3-8-27b", "qwen3.8-27b", 18000))
        self.assertEqual(s["args"]["max-model-len"], 262144)

    def register(self, served_name, **over):
        from tests.test_recipes import recipe
        c = recipe()["components"][0]
        d = {"id": "qwen3-8-27b", "served_name": served_name, "engine": "vllm", "port": 18000,
             "image": f"vllm/vllm-openai@{DIGEST}", "model": f"models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/{SHA}",
             "args": c["args"], "env": {}}
        d.update(over)
        (self.reg / f"{d['id']}.json").write_text(json.dumps(d))

    def test_a_recipe_runs_only_when_its_exact_spec_runs(self):
        # From Codex's review: the name alone said "running" for any instance serving it
        self.signed_recipe()
        self.register("qwen3.8-27b")
        [r] = json.loads(self.run_cli("recipes", "--json")[1])["recipes"]
        self.assertTrue(r["running"])
        self.register("qwen3.8-27b", args={"gpu-memory-utilization": 0.3})
        [r] = json.loads(self.run_cli("recipes", "--json")[1])["recipes"]
        self.assertFalse(r["running"])
        self.assertEqual(r["conflicts"], ["qwen3.8-27b"])

    def test_apply_refuses_to_replace_an_unrelated_instance(self):
        # "qwen3-8-27b" is the instance id of served name "qwen3.8-27b" and of "qwen3-8-27b" (Codex)
        self.signed_recipe()
        self.register("qwen3-8-27b", id="qwen3-8-27b")
        rc, _ = self.run_cli("recipe", "apply", "qwen38-27b-coder")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.helper_calls, [])

    def test_apply_may_restart_its_own_component(self):
        self.signed_recipe()
        self.register("qwen3.8-27b", args={"gpu-memory-utilization": 0.3})
        rc, _ = self.run_cli("recipe", "apply", "qwen38-27b-coder")
        self.assertEqual(rc, 0)
        self.assertEqual(self.helper_calls[0][0], ["start"])

    def test_recipe_stop_leaves_other_instances_alone(self):
        self.signed_recipe()
        self.register("qwen3.8-27b", id="someone-else", args={"gpu-memory-utilization": 0.3})
        self.run_cli("recipe", "stop", "qwen38-27b-coder")
        self.assertEqual(self.helper_calls, [])

    def test_recipe_stop_stops_its_instances(self):
        self.signed_recipe()
        self.register("qwen3.8-27b")
        self.run_cli("recipe", "stop", "qwen38-27b-coder")
        self.assertEqual(self.helper_calls, [(["stop", "qwen3-8-27b"], None)])

    def test_an_unknown_or_unsigned_recipe_is_refused(self):
        self.signed_recipe()
        for rid in ("nothing", "tampered"):
            rc, _ = self.run_cli("recipe", "apply", rid)
            self.assertNotEqual(rc, 0)
        self.assertEqual(self.helper_calls, [])

    def test_recipe_fetch_downloads_into_the_store(self):
        self.signed_recipe()
        ran = []
        self.env.run = lambda argv, env: ran.append((argv, env["HF_HOME"])) or 0
        rc, _ = self.run_cli("recipe", "fetch", "qwen38-27b-coder")
        self.assertEqual(rc, 0)
        [(argv, hf_home)] = ran
        self.assertEqual(argv[:3], ["hf", "download", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead"])
        self.assertEqual(hf_home, str(self.hf))

    def hub(self):
        from tests.test_hf import FakeHub
        self.fake = FakeHub()
        self.addCleanup(self.fake.server_close)
        self.addCleanup(self.fake.shutdown)
        self.env.hf_endpoint = f"http://127.0.0.1:{self.fake.server_address[1]}"
        self.spawned = []

        class P:
            pid = 777
        self.env.spawn = lambda argv, env, log: self.spawned.append((argv, env)) or P()
        self.env.downloads_dir = pathlib.Path(self.tmp.name) / "downloads"
        self.env.config_dir = pathlib.Path(self.tmp.name) / "config"

    def test_hub_search_and_files(self):
        self.hub()
        rc, out = self.run_cli("hub", "search", "qwen3.8", "--json")
        self.assertEqual([r["id"] for r in json.loads(out)], ["unsloth/Qwen3.8-27B-GGUF", "meta/secret"])
        rc, out = self.run_cli("hub", "files", "unsloth/Qwen3.8-27B-GGUF", "--json")
        d = json.loads(out)
        self.assertEqual(d["revision"], "a" * 40)
        self.assertEqual([v["name"] for v in d["variants"]], ["Q4_K_M", "Q8_0"])

    def test_download_a_variant_pins_the_commit(self):
        self.hub()
        rc, out = self.run_cli("download", "unsloth/Qwen3.8-27B-GGUF", "--variant", "Q4_K_M", "--json")
        self.assertEqual(rc, 0, out)
        [(argv, env)] = self.spawned
        self.assertEqual(argv, ["hf", "download", "unsloth/Qwen3.8-27B-GGUF", "--revision", "a" * 40,
                                "--include", "Qwen3.8-27B-Q4_K_M.gguf", "--include", "mmproj-F16.gguf"])
        rc, out = self.run_cli("downloads", "--json")
        [row] = json.loads(out)
        self.assertEqual((row["repo"], row["expected"]), ("unsloth/Qwen3.8-27B-GGUF", 16_900))

    def test_a_finished_variant_download_makes_the_model_ready(self):
        # a partial download is incomplete against the revision's full manifest, but complete for
        # what was asked (the Q4_K_M variant): models --json says so (seen on the Thor)
        self.hub()
        self.run_cli("download", "unsloth/Qwen3.8-27B-GGUF", "--variant", "Q4_K_M")
        root = put(self.hf / "hub", "unsloth/Qwen3.8-27B-GGUF", "a" * 40,
                   {"Qwen3.8-27B-Q4_K_M.gguf": b"q" * 16_000, "mmproj-F16.gguf": b"p" * 900})
        (root / "trees").mkdir()
        (root / "trees" / f"{'a' * 40}.json").write_text(json.dumps({"files": {
            "Qwen3.8-27B-Q4_K_M.gguf": {"size": 16_000}, "mmproj-F16.gguf": {"size": 900}, "big-Q8_0.gguf": {"size": 10**9}}}))
        self.env.spawn = None
        m = [x for x in json.loads(self.run_cli("models", "--json")[1]) if x["repo"] == "unsloth/Qwen3.8-27B-GGUF"][0]
        self.assertEqual(m["download"]["state"], "done")
        self.assertEqual(m["download"]["include"], ["Qwen3.8-27B-Q4_K_M.gguf", "mmproj-F16.gguf"])

    def test_an_unknown_variant_is_refused(self):
        self.hub()
        rc, _ = self.run_cli("download", "unsloth/Qwen3.8-27B-GGUF", "--variant", "Q2_K")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.spawned, [])

    def test_the_token_is_read_from_stdin_and_kept_private(self):
        self.hub()
        import sys, io, stat as st
        old = sys.stdin
        sys.stdin = io.StringIO("hf_secret\n")
        try:
            rc, out = self.run_cli("hf-token", "set")
        finally:
            sys.stdin = old
        tok = self.env.config_dir / "hf-token"
        self.assertEqual(tok.read_text().strip(), "hf_secret")
        self.assertEqual(st.S_IMODE(tok.stat().st_mode), 0o600)
        self.assertNotIn("hf_secret", out)
        self.run_cli("download", "unsloth/Qwen3.8-27B-GGUF", "--variant", "Q4_K_M")
        self.assertEqual(self.spawned[-1][1]["HF_TOKEN"], "hf_secret")
        self.assertIn("Bearer hf_secret", [a for _, a in self.fake.seen if a])
        self.run_cli("hf-token", "clear")
        self.assertFalse(tok.exists())

    def test_delete_refuses_a_model_in_use(self):
        self.hub()
        (self.reg / "q.json").write_text(json.dumps({"id": "q", "served_name": "q", "port": 18000,
            "model": f"models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/{SHA}"}))
        ran = []
        self.env.run = lambda argv, env: ran.append(argv) or 0
        rc, _ = self.run_cli("delete", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead")
        self.assertNotEqual(rc, 0)
        (self.reg / "q.json").unlink()
        rc, _ = self.run_cli("delete", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead")
        self.assertEqual(rc, 0)
        self.assertEqual(ran, [["hf", "cache", "rm", "model/RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", "-y"]])

    def test_delete_one_revision(self):
        # From Codex's review: the app confirms one revision, so only that revision goes
        self.hub()
        other = "c" * 40
        (self.reg / "q.json").write_text(json.dumps({"id": "q", "served_name": "q", "port": 18000,
            "model": f"models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/{other}"}))
        ran = []
        self.env.run = lambda argv, env: ran.append(argv) or 0
        rc, _ = self.run_cli("delete", f"RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead@{SHA}")
        self.assertEqual(rc, 0)           # another revision is in use, not this one
        self.assertEqual(ran, [["hf", "cache", "rm", SHA, "-y"]])
        rc, _ = self.run_cli("delete", f"RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead@{other}")
        self.assertNotEqual(rc, 0)
        rc, _ = self.run_cli("delete", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead@main")
        self.assertNotEqual(rc, 0)        # a revision is a full commit

    def test_delete_by_revision_stays_in_its_repo(self):
        # From Codex's re-review: hf cache rm SHA finds the SHA anywhere in the cache, so
        # `delete A@<B's commit>` must not get past the in-use check on A and delete B
        self.hub()
        b = "d" * 40
        (self.reg / "b.json").write_text(json.dumps({"id": "b", "served_name": "b", "port": 18000,
            "model": f"models--nvidia--B/snapshots/{b}"}))
        ran = []
        self.env.run = lambda argv, env: ran.append(argv) or 0
        rc, _ = self.run_cli("delete", f"RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead@{b}")
        self.assertNotEqual(rc, 0)
        self.assertEqual(ran, [])

    def test_stats_json(self):
        (self.reg / "q.json").write_text(json.dumps({"id": "q", "served_name": "qwen3.8-27b", "port": 18000}))
        self.env.counters = lambda url: {"generation_tokens": 10.0} if ":18000/" in url else None
        self.env.meminfo = lambda: {"total": 100, "available": 40}
        rc, out = self.run_cli("stats", "--json")
        d = json.loads(out)
        self.assertEqual(d["memory"], {"total": 100, "available": 40})
        self.assertEqual(d["instances"], [{"id": "q", "served_name": "qwen3.8-27b", "counters": {"generation_tokens": 10.0}}])
        self.assertIn("time", d)

    def test_engines_json(self):
        rc, out = self.run_cli("engines", "--json")
        e = {x["engine"]: x for x in json.loads(out)}
        self.assertEqual(e["vllm"]["image"], f"vllm/vllm-openai@{DIGEST}")
        self.assertTrue(e["vllm"]["configured"])

    def test_agents_json_lists_the_catalog(self):
        rc, out = self.run_cli("agents", "--json")
        ids = [a["id"] for a in json.loads(out)]
        self.assertIn("opencode", ids)
        self.assertIn("gemini", ids)

    def test_agents_json_says_which_are_connected(self):
        (self.reg / "qwen.json").write_text(json.dumps(
            {"id": "qwen", "served_name": "qwen3.8-27b", "port": 18000, "engine": "vllm", "args": {"max-model-len": 131072}}))
        self.run_cli("agent", "connect", "crush")
        got = {a["id"]: a.get("connected") for a in json.loads(self.run_cli("agents", "--json")[1])}
        self.assertEqual((got["crush"], got["opencode"], got["gemini"]), (True, False, None))


if __name__ == "__main__":
    unittest.main()
