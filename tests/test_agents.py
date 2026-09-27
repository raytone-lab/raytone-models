"""Agent adapters point a coding agent at the router. Each writes only its agent's own config,
keeps the original byte for byte, and can put it back."""
import json
import os
import pathlib
import stat
import tempfile
import unittest

from raytone_models import agents

MODELS = [{"id": "qwen3.8-27b", "context": 131072, "output": 32768}]
BASE = "http://127.0.0.1:8090/v1"


class OpencodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.home, self.state = t / "home", t / "state"
        self.cfg = self.home / ".config" / "opencode" / "opencode.json"
        self.a = agents.get("opencode", home=self.home, state=self.state)

    def tearDown(self):
        self.tmp.cleanup()

    def test_connect_without_a_config(self):
        self.a.connect(MODELS, default="qwen3.8-27b", base_url=BASE)
        c = json.loads(self.cfg.read_text())
        p = c["provider"]["raytone"]
        self.assertEqual(p["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(p["options"]["baseURL"], BASE)
        self.assertEqual(p["models"]["qwen3.8-27b"]["limit"], {"context": 131072, "output": 32768})
        self.assertEqual(c["model"], "raytone/qwen3.8-27b")
        self.assertEqual(self.a.status()["connected"], True)
        self.a.revert()
        self.assertFalse(self.cfg.exists())
        self.assertEqual(self.a.status()["connected"], False)

    def test_an_existing_config_is_kept_and_restored_exactly(self):
        self.cfg.parent.mkdir(parents=True)
        original = b'{\n  "$schema": "https://opencode.ai/config.json",\n  "theme": "tokyonight",\n  "provider": {"other": {"npm": "x"}}\n}\n'
        self.cfg.write_bytes(original)
        os.chmod(self.cfg, 0o600)
        self.a.connect(MODELS, default="qwen3.8-27b", base_url=BASE)
        c = json.loads(self.cfg.read_text())
        self.assertEqual(c["theme"], "tokyonight")
        self.assertIn("other", c["provider"])
        self.assertEqual(stat.S_IMODE(self.cfg.stat().st_mode), 0o600)
        # connecting again (another model) must not replace the saved original
        self.a.connect(MODELS + [{"id": "muse", "context": 65536, "output": 8192}], default="muse", base_url=BASE)
        self.a.revert()
        self.assertEqual(self.cfg.read_bytes(), original)

    def test_a_config_it_cannot_parse_is_left_alone(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text("{ // a comment opencode would read, we would lose\n}")
        with self.assertRaises(agents.AgentError):
            self.a.connect(MODELS, default="qwen3.8-27b", base_url=BASE)
        self.assertIn("a comment", self.cfg.read_text())

    def test_the_default_must_be_one_of_the_models(self):
        with self.assertRaises(agents.AgentError):
            self.a.connect(MODELS, default="gpt-5", base_url=BASE)
        self.assertFalse(self.cfg.exists())

    def test_revert_without_connect_is_harmless(self):
        self.a.revert()
        self.assertFalse(self.cfg.exists())


class JsonAdapterTests(unittest.TestCase):
    """Claude Code, Crush and Pi keep their settings in JSON: merged in, restored exactly."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.home, self.state = t / "home", t / "state"

    def tearDown(self):
        self.tmp.cleanup()

    def roundtrip(self, agent_id, rel, original):
        path = self.home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)
        a = agents.get(agent_id, home=self.home, state=self.state)
        a.connect(MODELS, default="qwen3.8-27b", base_url=BASE)
        cfg = json.loads(path.read_text())
        a.revert()
        self.assertEqual(path.read_bytes(), original)
        return cfg

    def test_claude_code_uses_the_anthropic_endpoint(self):
        cfg = self.roundtrip("claude", ".claude/settings.json", b'{"theme": "dark", "env": {"FOO": "1"}}\n')
        env = cfg["env"]
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:8090")      # no /v1: Claude Code adds it
        self.assertTrue(env["ANTHROPIC_AUTH_TOKEN"])
        for tier in ("OPUS", "SONNET", "HAIKU"):
            self.assertEqual(env[f"ANTHROPIC_DEFAULT_{tier}_MODEL"], "qwen3.8-27b")
        self.assertEqual(env["CLAUDE_CODE_ATTRIBUTION_HEADER"], "0")               # keeps prefix caching working
        self.assertEqual(env["FOO"], "1")
        self.assertEqual(cfg["theme"], "dark")

    def test_crush_gets_an_openai_compatible_provider(self):
        cfg = self.roundtrip("crush", ".config/crush/crush.json", b'{"options": {"debug": false}}\n')
        p = cfg["providers"]["raytone"]
        self.assertEqual((p["type"], p["base_url"]), ("openai-compat", BASE))
        self.assertEqual(p["models"][0]["id"], "qwen3.8-27b")
        self.assertEqual(p["models"][0]["context_window"], 131072)
        self.assertEqual(cfg["models"]["large"], {"model": "qwen3.8-27b", "provider": "raytone"})
        self.assertIn("options", cfg)

    def test_pi_gets_a_provider(self):
        cfg = self.roundtrip("pi", ".pi/agent/models.json", b'{"providers": {"other": {}}}\n')
        p = cfg["providers"]["raytone"]
        self.assertEqual((p["baseUrl"], p["api"]), (BASE, "openai-completions"))
        self.assertEqual(p["models"][0], {"id": "qwen3.8-27b", "contextWindow": 131072, "maxTokens": 32768})
        self.assertIn("other", cfg["providers"])

    def test_catalog_marks_the_agents_with_adapters(self):
        info = {a["id"]: a for a in agents.catalog()}
        for name in ("opencode", "claude", "crush", "pi"):
            self.assertTrue(info[name]["connectable"], name)
        self.assertFalse(info["gemini"]["connectable"])


class CatalogTests(unittest.TestCase):
    def test_unsupported_agents_say_why(self):
        info = {a["id"]: a for a in agents.catalog()}
        for name in ("gemini", "cursor-agent", "muse"):
            self.assertFalse(info[name]["supported"])
            self.assertTrue(info[name]["reason"])
        self.assertTrue(info["opencode"]["supported"])


if __name__ == "__main__":
    unittest.main()
