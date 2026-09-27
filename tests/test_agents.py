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


class CatalogTests(unittest.TestCase):
    def test_unsupported_agents_say_why(self):
        info = {a["id"]: a for a in agents.catalog()}
        for name in ("gemini", "cursor-agent", "muse"):
            self.assertFalse(info[name]["supported"])
            self.assertTrue(info[name]["reason"])
        self.assertTrue(info["opencode"]["supported"])


if __name__ == "__main__":
    unittest.main()
