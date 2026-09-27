"""Agent adapters: point Omarchy's coding agents at the router.

An adapter writes only its agent's own config file. Before its first change it saves the file
as it was (or notes that there was none), in the manager's state directory; revert() puts that
back byte for byte. A config it cannot parse is left alone rather than rewritten.
"""
import json
import os
import pathlib
import shutil
import tempfile

STATE = pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state")) / "raytone-models/agents"
ROUTER = "http://127.0.0.1:8090/v1"

# Omarchy 4.0.4's agents (omarchy-default-agent) and whether they can use a local endpoint.
CATALOG = [
    ("opencode", "OpenCode", True, ""),
    ("claude", "Claude Code", True, ""),
    ("codex", "Codex", True, "through CC Switch, which turns Codex's Responses API into chat completions"),
    ("crush", "Crush", True, ""),
    ("pi", "Pi", True, ""),
    ("omp", "Oh My Pi", True, ""),
    ("hermes", "Hermes", True, ""),
    ("openclaw", "OpenClaw", True, ""),
    ("grok", "Grok", True, ""),
    ("copilot", "GitHub Copilot", True, ""),
    ("gemini", "Gemini", False, "speaks only Google's Gemini API"),
    ("cursor-agent", "Cursor CLI", False, "sends every request through Cursor's cloud"),
    ("muse", "Muse Code", False, "uses only Meta-hosted models"),
]


class AgentError(RuntimeError):
    pass


def catalog():
    return [{"id": i, "name": n, "supported": s, "connectable": i in ADAPTERS,
             "reason": r if not s else "", "note": r if s else ""} for i, n, s, r in CATALOG]


def _atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


class Adapter:
    id = ""

    def __init__(self, home=None, state=None):
        self.home = pathlib.Path(home or pathlib.Path.home())
        self.state = pathlib.Path(state or STATE) / self.id

    @property
    def path(self):
        raise NotImplementedError

    def _save_original(self):
        """Keep the config as it was before our first change; later connects keep that copy."""
        marker = self.state / "original.json"
        if marker.exists():
            return
        self.state.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        if existed:
            shutil.copy2(self.path, self.state / "original")
        marker.write_text(json.dumps({"path": str(self.path), "existed": existed,
                                      "mode": self.path.stat().st_mode & 0o7777 if existed else 0o600}))

    def revert(self):
        marker = self.state / "original.json"
        if not marker.exists():
            return
        m = json.loads(marker.read_text())
        if m["existed"]:
            _atomic_write(self.path, (self.state / "original").read_bytes(), m["mode"])
        else:
            self.path.unlink(missing_ok=True)
        shutil.rmtree(self.state)

    def status(self):
        return {"id": self.id, "connected": (self.state / "original.json").exists(), "config": str(self.path)}


class JsonAdapter(Adapter):
    """An agent whose settings are one JSON file: parse it (or refuse), keep the original, merge."""
    rel = ""

    @property
    def path(self):
        return self.home / self.rel

    def merge(self, cfg, models, default, base_url):
        raise NotImplementedError

    def connect(self, models, *, default, base_url=ROUTER):
        if default not in {m["id"] for m in models}:
            raise AgentError(f"{default} is not one of the running models")
        cfg = {}
        if self.path.exists():
            try:
                cfg = json.loads(self.path.read_text())
            except ValueError:
                raise AgentError(f"{self.path} is not plain JSON; left as it is") from None
            if not isinstance(cfg, dict):
                raise AgentError(f"{self.path} is not a JSON object; left as it is")
        mode = self.path.stat().st_mode & 0o7777 if self.path.exists() else 0o600
        self._save_original()
        self.merge(cfg, models, default, base_url)
        _atomic_write(self.path, (json.dumps(cfg, indent=2) + "\n").encode(), mode)


class Opencode(JsonAdapter):
    """~/.config/opencode/opencode.json: a provider through @ai-sdk/openai-compatible (chat completions)."""
    id, rel = "opencode", ".config/opencode/opencode.json"

    def merge(self, cfg, models, default, base_url):
        cfg.setdefault("$schema", "https://opencode.ai/config.json")
        cfg.setdefault("provider", {})["raytone"] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Raytone Models (local)",
            "options": {"baseURL": base_url},
            "models": {m["id"]: {"name": m["id"], "limit": {"context": m["context"], "output": m["output"]}}
                       for m in models},
        }
        cfg["model"] = f"raytone/{default}"


class Claude(JsonAdapter):
    """~/.claude/settings.json env: the Anthropic Messages API, which the engines serve natively."""
    id, rel = "claude", ".claude/settings.json"

    def merge(self, cfg, models, default, base_url):
        # an explicit model (settings or ANTHROPIC_MODEL) wins over the aliases: point it here too
        cfg["model"] = default
        env = cfg.setdefault("env", {})
        env.update({
            "ANTHROPIC_MODEL": default,
            "ANTHROPIC_BASE_URL": base_url.removesuffix("/v1"),
            "ANTHROPIC_AUTH_TOKEN": "raytone-local",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": default,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": default,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": default,
            # a per-request hash in the system prompt would defeat the engine's prefix cache
            "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
            "API_TIMEOUT_MS": "3000000",
            # Claude Code's default effort ("high") is not one every template knows; "medium" is common
            "CLAUDE_CODE_EFFORT_LEVEL": "medium",
        })


class Crush(JsonAdapter):
    """~/.config/crush/crush.json: an openai-compat provider, used for the large and small models."""
    id, rel = "crush", ".config/crush/crush.json"

    def merge(self, cfg, models, default, base_url):
        cfg.setdefault("$schema", "https://charm.land/crush.json")
        cfg.setdefault("providers", {})["raytone"] = {
            "type": "openai-compat", "name": "Raytone Models (local)", "base_url": base_url, "api_key": "raytone-local",
            "models": [{"id": m["id"], "name": m["id"], "context_window": m["context"], "default_max_tokens": m["output"]}
                       for m in models],
        }
        cfg.setdefault("models", {})
        for size in ("large", "small"):
            cfg["models"][size] = {"model": default, "provider": "raytone"}


class Pi(JsonAdapter):
    """~/.pi/agent/models.json: a provider with the openai-completions API; pick it in /model."""
    id, rel = "pi", ".pi/agent/models.json"

    def merge(self, cfg, models, default, base_url):
        cfg.setdefault("providers", {})["raytone"] = {
            "baseUrl": base_url, "api": "openai-completions", "apiKey": "raytone-local",
            "models": [{"id": m["id"], "contextWindow": m["context"], "maxTokens": m["output"]} for m in models],
        }


ADAPTERS = {a.id: a for a in (Opencode, Claude, Crush, Pi)}


def get(agent_id, **kw):
    try:
        return ADAPTERS[agent_id](**kw)
    except KeyError:
        raise AgentError(f"no adapter for {agent_id}") from None
