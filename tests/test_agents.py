"""Agent adapters point a coding agent at the router. Each writes only its agent's own config,
keeps the original byte for byte, and can put it back.

An agent is never tied to a model: it knows one address and one name, local, which the router
points at whatever model runs. The context length is the engine's, set when the model starts;
agents are given none (a request too long for it is the engine's error to report)."""
import json
import os
import pathlib
import stat
import tempfile
import unittest

from raytone_models import agents

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
        self.a.connect(base_url=BASE)
        c = json.loads(self.cfg.read_text())
        p = c["provider"]["raytone"]
        self.assertEqual(p["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(p["options"]["baseURL"], BASE)
        self.assertEqual(p["models"], {"local": {"name": "Local model (Raytone Models)"}})
        self.assertEqual(c["model"], "raytone/local")
        self.assertEqual(self.a.status()["connected"], True)
        self.a.revert()
        self.assertFalse(self.cfg.exists())
        self.assertEqual(self.a.status()["connected"], False)

    def test_an_existing_config_is_kept_and_restored_exactly(self):
        self.cfg.parent.mkdir(parents=True)
        original = b'{\n  "$schema": "https://opencode.ai/config.json",\n  "theme": "tokyonight",\n  "provider": {"other": {"npm": "x"}}\n}\n'
        self.cfg.write_bytes(original)
        os.chmod(self.cfg, 0o600)
        self.a.connect(base_url=BASE)
        c = json.loads(self.cfg.read_text())
        self.assertEqual(c["theme"], "tokyonight")
        self.assertIn("other", c["provider"])
        self.assertEqual(stat.S_IMODE(self.cfg.stat().st_mode), 0o600)
        # connecting again must not replace the saved original
        self.a.connect(base_url=BASE)
        self.a.revert()
        self.assertEqual(self.cfg.read_bytes(), original)

    def test_a_config_it_cannot_parse_is_left_alone(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text("{ // a comment opencode would read, we would lose\n}")
        with self.assertRaises(agents.AgentError):
            self.a.connect(base_url=BASE)
        self.assertIn("a comment", self.cfg.read_text())

    def test_connecting_needs_no_running_model(self):
        # the name is fixed: an agent can be connected before any model starts
        self.a.connect()
        self.assertEqual(json.loads(self.cfg.read_text())["provider"]["raytone"]["options"]["baseURL"], agents.ROUTER)

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
        a.connect(base_url=BASE)
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
            self.assertEqual(env[f"ANTHROPIC_DEFAULT_{tier}_MODEL"], "local")
        self.assertEqual(env["CLAUDE_CODE_ATTRIBUTION_HEADER"], "0")               # keeps prefix caching working
        # Claude Code asks for effort "high"; Qwen3.8's template knows xhigh, medium and low (seen on the Thor)
        self.assertEqual(env["CLAUDE_CODE_EFFORT_LEVEL"], "medium")
        self.assertEqual(env["FOO"], "1")
        self.assertEqual(cfg["theme"], "dark")

    def test_claude_code_model_choice_follows_the_connect(self):
        # a full model name in settings would bypass the aliases and ask the router for it (Codex)
        cfg = self.roundtrip("claude", ".claude/settings.json",
                             b'{"model": "claude-opus-4-7", "env": {"ANTHROPIC_MODEL": "claude-opus-4-7"}}\n')
        self.assertEqual(cfg["model"], "local")
        self.assertEqual(cfg["env"]["ANTHROPIC_MODEL"], "local")

    def test_crush_gets_an_openai_compatible_provider(self):
        cfg = self.roundtrip("crush", ".config/crush/crush.json", b'{"options": {"debug": false}}\n')
        p = cfg["providers"]["raytone"]
        self.assertEqual((p["type"], p["base_url"]), ("openai-compat", BASE))
        self.assertEqual(p["models"], [{"id": "local", "name": "Local model (Raytone Models)"}])
        self.assertEqual(cfg["models"]["large"], {"model": "local", "provider": "raytone"})
        self.assertIn("options", cfg)

    def test_pi_gets_a_provider(self):
        cfg = self.roundtrip("pi", ".pi/agent/models.json", b'{"providers": {"other": {}}}\n')
        p = cfg["providers"]["raytone"]
        self.assertEqual((p["baseUrl"], p["api"]), (BASE, "openai-completions"))
        self.assertEqual(p["models"], [{"id": "local", "name": "Local model (Raytone Models)"}])
        self.assertIn("other", cfg["providers"])

    def test_hermes_gets_a_custom_provider(self):
        # ~/.hermes/config.yaml, written as JSON (which is YAML); Hermes needs no key on loopback
        cfg = self.roundtrip("hermes", ".hermes/config.yaml", b'{"toolsets": ["hermes-cli"], "model": {"provider": "nous"}}\n')
        self.assertEqual(cfg["model"], {"provider": "custom", "base_url": BASE, "default": "local"})
        self.assertEqual(cfg["toolsets"], ["hermes-cli"])

    def test_a_hermes_config_in_yaml_is_left_alone(self):
        path = self.home / ".hermes/config.yaml"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"model:\n  provider: nous\n")
        with self.assertRaises(agents.AgentError):
            agents.get("hermes", home=self.home, state=self.state).connect(base_url=BASE)
        self.assertEqual(path.read_bytes(), b"model:\n  provider: nous\n")

    def test_oh_my_pi_gets_a_provider_in_models_yml(self):
        # Oh My Pi reads models.yml (it converts a models.json once, then reads only the YAML);
        # written as JSON, which is YAML
        cfg = self.roundtrip("omp", ".omp/agent/models.yml", b'{"providers": {"other": {}}}\n')
        p = cfg["providers"]["raytone"]
        self.assertEqual((p["baseUrl"], p["api"]), (BASE, "openai-completions"))
        self.assertEqual(p["models"], [{"id": "local", "name": "Local model (Raytone Models)"}])
        self.assertIn("other", cfg["providers"])

    def test_oh_my_pi_keeps_the_providers_of_a_models_json(self):
        # with no models.yml yet, the YAML we write replaces models.json for Oh My Pi: carry it over
        old = self.home / ".omp/agent/models.json"
        old.parent.mkdir(parents=True)
        old.write_bytes(b'{"providers": {"mine": {"baseUrl": "http://x"}}}')
        a = agents.get("omp", home=self.home, state=self.state)
        a.connect(base_url=BASE)
        cfg = json.loads((self.home / ".omp/agent/models.yml").read_text())
        self.assertEqual(sorted(cfg["providers"]), ["mine", "raytone"])
        a.revert()
        self.assertFalse((self.home / ".omp/agent/models.yml").exists())
        self.assertEqual(old.read_bytes(), b'{"providers": {"mine": {"baseUrl": "http://x"}}}')

    def test_catalog_marks_the_agents_with_adapters(self):
        info = {a["id"]: a for a in agents.catalog()}
        for name in ("opencode", "claude", "crush", "pi", "hermes", "omp"):
            self.assertTrue(info[name]["connectable"], name)
        self.assertFalse(info["gemini"]["connectable"])


class CodexTests(unittest.TestCase):
    """Codex keeps its settings in TOML (~/.codex/config.toml) and speaks the Responses API, which
    vLLM and SGLang serve and the router forwards: a custom provider, no proxy in between."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.home, self.state = t / "home", t / "state"
        self.path = self.home / ".codex/config.toml"
        self.a = agents.get("codex", home=self.home, state=self.state)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        import tomllib
        return tomllib.loads(self.path.read_text())

    def test_connect_without_a_config(self):
        self.a.connect(base_url=BASE)
        cfg = self.read()
        self.assertEqual((cfg["model"], cfg["model_provider"]), ("local", "raytone"))
        p = cfg["model_providers"]["raytone"]
        self.assertEqual((p["base_url"], p["wire_api"]), (BASE, "responses"))
        self.assertNotIn("env_key", p)                # the router needs no key
        self.assertNotIn("model_context_window", cfg)
        self.a.revert()
        self.assertFalse(self.path.exists())

    def test_an_existing_config_is_kept_and_restored_exactly(self):
        original = (b'# my settings\nmodel = "gpt-6"\napproval_policy = "on-request"\n\n'
                    b'[model_providers.raytone]\nname = "old"\nbase_url = "http://old"\n\n'
                    b'[mcp_servers.docs]\ncommand = "docs-mcp"\nargs = ["--x"]\n')
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(original)
        self.a.connect(base_url=BASE)
        cfg = self.read()
        self.assertEqual(cfg["model"], "local")
        self.assertEqual(cfg["approval_policy"], "on-request")
        self.assertEqual(cfg["mcp_servers"]["docs"], {"command": "docs-mcp", "args": ["--x"]})
        self.assertEqual(cfg["model_providers"]["raytone"]["base_url"], BASE)
        # connecting again replaces our own lines, it does not repeat them
        self.a.connect(base_url=BASE)
        self.assertEqual(self.path.read_text().count("[model_providers.raytone]"), 1)
        once = self.path.read_bytes()
        self.a.connect(base_url=BASE)
        self.assertEqual(self.path.read_bytes(), once)             # reconnecting changes nothing
        self.assertEqual(self.path.read_text().count("# Raytone Models"), 1)
        self.a.revert()
        self.assertEqual(self.path.read_bytes(), original)

    def test_a_config_it_cannot_parse_is_left_alone(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"model = [unclosed\n")
        with self.assertRaises(agents.AgentError):
            self.a.connect(base_url=BASE)
        self.assertEqual(self.path.read_bytes(), b"model = [unclosed\n")

    def test_a_multi_line_string_is_never_edited(self):
        # From Codex's review of PR #8: lines inside a multi-line string look like keys and tables;
        # the edit must change nothing but our own settings, or not happen at all
        for original in (b'developer_instructions = """\nmodel = example\nKeep this.\n"""\n',
                         b'model = """\napproval_policy = "never"\n# """\n',
                         b'notes = """\n[model_providers.raytone]\nkeep me\n"""\n'):
            with self.subTest(original=original):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_bytes(original)
                with self.assertRaises(agents.AgentError):
                    self.a.connect(base_url=BASE)
                self.assertEqual(self.path.read_bytes(), original)

    def test_codex_is_connectable_now(self):
        row = next(r for r in agents.catalog() if r["id"] == "codex")
        self.assertTrue(row["supported"])


class EnvAdapterTests(unittest.TestCase):
    """Copilot CLI takes a custom endpoint from its environment only. From Codex's review of PR #10:
    not the session's environment (environment.d reaches every program and outlives a revert), but
    variables of our own that `raytone-models agent-exec copilot` (and Launch) start it with."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.home, self.state = t / "home", t / "state"

    def tearDown(self):
        self.tmp.cleanup()

    def test_copilot_uses_its_byok_variables_offline(self):
        a = agents.get("copilot", home=self.home, state=self.state)
        a.connect(base_url=BASE)
        path = self.home / ".config/raytone-models/agents/copilot.env"
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertFalse((self.home / ".config/environment.d").exists())
        env = dict(l.split("=", 1) for l in path.read_text().splitlines() if l and not l.startswith("#"))
        self.assertEqual(env, {"COPILOT_PROVIDER_TYPE": "openai", "COPILOT_PROVIDER_BASE_URL": BASE,
                               "COPILOT_MODEL": "local", "COPILOT_OFFLINE": "true"})
        self.assertEqual(a.env(), env)
        a.revert()
        self.assertFalse(path.exists())
        self.assertEqual(a.env(), {})

    def test_an_existing_file_is_restored(self):
        path = self.home / ".config/raytone-models/agents/copilot.env"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"MINE=1\n")
        a = agents.get("copilot", home=self.home, state=self.state)
        a.connect(base_url=BASE)
        a.revert()
        self.assertEqual(path.read_bytes(), b"MINE=1\n")


class CatalogTests(unittest.TestCase):
    def test_unsupported_agents_say_why(self):
        info = {a["id"]: a for a in agents.catalog()}
        for name in ("gemini", "cursor-agent", "muse"):
            self.assertFalse(info[name]["supported"])
            self.assertTrue(info[name]["reason"])
        self.assertTrue(info["opencode"]["supported"])


if __name__ == "__main__":
    unittest.main()
