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
        put(self.hf / "hub", "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead", SHA, {"config.json": b"{}", "m.safetensors": b"w"})
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

    def test_agents_json_lists_the_catalog(self):
        rc, out = self.run_cli("agents", "--json")
        ids = [a["id"] for a in json.loads(out)]
        self.assertIn("opencode", ids)
        self.assertIn("gemini", ids)


if __name__ == "__main__":
    unittest.main()
