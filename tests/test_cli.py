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

    def test_agents_json_lists_the_catalog(self):
        rc, out = self.run_cli("agents", "--json")
        ids = [a["id"] for a in json.loads(out)]
        self.assertIn("opencode", ids)
        self.assertIn("gemini", ids)


if __name__ == "__main__":
    unittest.main()
