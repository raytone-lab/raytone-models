"""Agent adapters: point Omarchy's coding agents at the router.

An adapter writes only its agent's own config file. Before its first change it saves the file
as it was (or notes that there was none), in the manager's state directory; revert() puts that
back byte for byte. A config it cannot parse is left alone rather than rewritten.

An agent is never tied to a model: it gets the router's address and one fixed name, local, which
the router points at the model running now. The context length belongs to the engine (set when the
model starts), so none is written here.
"""
import json
import os
import pathlib
import re
import shutil
import tempfile
import tomllib

STATE = pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state")) / "raytone-models/agents"
ROUTER = "http://127.0.0.1:8090/v1"
MODEL = "local"                        # router.ALIAS
LABEL = "Local model (Raytone Models)"

# Omarchy 4.0.4's agents (omarchy-default-agent) and whether they can use a local endpoint.
CATALOG = [
    ("opencode", "OpenCode", True, ""),
    ("claude", "Claude Code", True, ""),
    ("codex", "Codex", True, "through the Responses API, which vLLM and SGLang serve"),
    ("crush", "Crush", True, ""),
    ("pi", "Pi", True, ""),
    ("omp", "Oh My Pi", True, ""),
    ("hermes", "Hermes", True, ""),
    ("openclaw", "OpenClaw", True, ""),
    ("grok", "Grok", True, ""),
    ("copilot", "GitHub Copilot", True, "through its BYOK variables, offline: start it with raytone-models agent-exec copilot"),
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
    seed = ""       # read instead while the config does not exist yet (that file itself is left as it is)

    @property
    def path(self):
        return self.home / self.rel

    def merge(self, cfg, base_url):
        raise NotImplementedError

    def connect(self, *, base_url=ROUTER):
        cfg = {}
        source = self.path if self.path.exists() else self.home / self.seed if self.seed else None
        if source is not None and source.exists():
            try:
                cfg = json.loads(source.read_text())
            except ValueError:
                raise AgentError(f"{source} is not plain JSON; left as it is") from None
            if not isinstance(cfg, dict):
                raise AgentError(f"{source} is not a JSON object; left as it is")
        mode = self.path.stat().st_mode & 0o7777 if self.path.exists() else 0o600
        self._save_original()
        self.merge(cfg, base_url)
        _atomic_write(self.path, (json.dumps(cfg, indent=2) + "\n").encode(), mode)


class Opencode(JsonAdapter):
    """~/.config/opencode/opencode.json: a provider through @ai-sdk/openai-compatible (chat completions)."""
    id, rel = "opencode", ".config/opencode/opencode.json"

    def merge(self, cfg, base_url):
        cfg.setdefault("$schema", "https://opencode.ai/config.json")
        cfg.setdefault("provider", {})["raytone"] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Raytone Models (local)",
            "options": {"baseURL": base_url},
            "models": {MODEL: {"name": LABEL}},
        }
        cfg["model"] = f"raytone/{MODEL}"


class Claude(JsonAdapter):
    """~/.claude/settings.json env: the Anthropic Messages API, which the engines serve natively."""
    id, rel = "claude", ".claude/settings.json"

    def merge(self, cfg, base_url):
        # an explicit model (settings or ANTHROPIC_MODEL) wins over the aliases: point it here too
        cfg["model"] = MODEL
        env = cfg.setdefault("env", {})
        env.update({
            "ANTHROPIC_MODEL": MODEL,
            "ANTHROPIC_BASE_URL": base_url.removesuffix("/v1"),
            "ANTHROPIC_AUTH_TOKEN": "raytone-local",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
            # a per-request hash in the system prompt would defeat the engine's prefix cache
            "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
            "API_TIMEOUT_MS": "3000000",
            # Claude Code's default effort ("high") is not one every template knows; "medium" is common
            "CLAUDE_CODE_EFFORT_LEVEL": "medium",
        })


class Crush(JsonAdapter):
    """~/.config/crush/crush.json: an openai-compat provider, used for the large and small models."""
    id, rel = "crush", ".config/crush/crush.json"

    def merge(self, cfg, base_url):
        cfg.setdefault("$schema", "https://charm.land/crush.json")
        cfg.setdefault("providers", {})["raytone"] = {
            "type": "openai-compat", "name": "Raytone Models (local)", "base_url": base_url, "api_key": "raytone-local",
            "models": [{"id": MODEL, "name": LABEL}],
        }
        cfg.setdefault("models", {})
        for size in ("large", "small"):
            cfg["models"][size] = {"model": MODEL, "provider": "raytone"}


class Pi(JsonAdapter):
    """~/.pi/agent/models.json: a provider with the openai-completions API; pick it in /model."""
    id, rel = "pi", ".pi/agent/models.json"

    def merge(self, cfg, base_url):
        cfg.setdefault("providers", {})["raytone"] = {
            "baseUrl": base_url, "api": "openai-completions", "apiKey": "raytone-local",
            "models": [{"id": MODEL, "name": LABEL}],
        }


class Omp(Pi):
    """Oh My Pi, Pi's fork: ~/.omp/agent/models.yml, written as JSON (which is YAML). It converts a
    models.json to models.yml once and then reads only the YAML, so a models.json is carried over."""
    id, rel, seed = "omp", ".omp/agent/models.yml", ".omp/agent/models.json"


class Hermes(JsonAdapter):
    """~/.hermes/config.yaml: its custom provider (an OpenAI-compatible endpoint; no key on loopback).
    Written as JSON, which is YAML; a config in YAML proper is not ours to rewrite."""
    id, rel = "hermes", ".hermes/config.yaml"

    def merge(self, cfg, base_url):
        cfg["model"] = {"provider": "custom", "base_url": base_url, "default": MODEL}


class Codex(Adapter):
    """~/.codex/config.toml: a custom provider on the Responses API. TOML has no writer in the
    standard library, so the file is edited as text: our top-level keys and our provider table are
    replaced, everything else stays, and the result must parse to exactly what was meant."""
    id = "codex"
    # model_context_window: an older connect wrote it; the engine's own limit applies now
    KEYS = re.compile(r"^\s*(model|model_provider|model_context_window)\s*=")
    NOTE = "# Raytone Models (raytone-models agent revert codex puts the original back)\n"
    HEADER = re.compile(r"^\s*\[")
    OURS = re.compile(r"^\s*\[\s*model_providers\s*\.\s*raytone\s*\]\s*(#.*)?$")

    @property
    def path(self):
        return self.home / ".codex/config.toml"

    def _edit(self, text, base_url):
        lines = text.splitlines(keepends=True)
        first = next((i for i, l in enumerate(lines) if self.HEADER.match(l)), len(lines))
        top = [l for l in lines[:first] if not self.KEYS.match(l) and l != self.NOTE]
        rest, skipping = [], False
        for l in lines[first:]:
            if self.HEADER.match(l):
                skipping = bool(self.OURS.match(l))
            if not skipping:
                rest.append(l)
        mine = [self.NOTE,
                f"model = {json.dumps(MODEL)}\n", 'model_provider = "raytone"\n']
        table = ["\n[model_providers.raytone]\n", 'name = "Raytone Models"\n', f"base_url = {json.dumps(base_url)}\n",
                 'wire_api = "responses"\n']
        body = "".join(top + rest).lstrip("\n")        # the blank line after our lines is ours
        return "".join(mine) + ("\n" if body.strip() else "") + body.rstrip("\n") + ("\n" if body.strip() else "") + "".join(table)

    def connect(self, *, base_url=ROUTER):
        text = self.path.read_text() if self.path.exists() else ""
        try:
            before = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            raise AgentError(f"{self.path} is not valid TOML; left as it is") from None
        if not isinstance(before.get("model_providers", {}), dict):
            raise AgentError(f"{self.path}: model_providers is not a table; left as it is")
        new = self._edit(text, base_url)
        # the whole configuration afterwards must be the one before with our settings in it and
        # nothing else changed (a line inside a multi-line string only looks like a key)
        expected = dict(before, model=MODEL, model_provider="raytone")
        expected.pop("model_context_window", None)
        expected["model_providers"] = dict(before.get("model_providers", {}),
                                           raytone={"name": "Raytone Models", "base_url": base_url, "wire_api": "responses"})
        try:
            ok = tomllib.loads(new) == expected
        except tomllib.TOMLDecodeError:
            ok = False
        if not ok:
            raise AgentError(f"{self.path} has a layout this adapter cannot edit safely; left as it is")
        mode = self.path.stat().st_mode & 0o7777 if self.path.exists() else 0o600
        self._save_original()
        _atomic_write(self.path, new.encode(), mode)


class EnvAdapter(Adapter):
    """An agent that takes a custom endpoint from its environment only. The variables are ours
    (~/.config/raytone-models/agents/ID.env, 0600) and reach the agent only when it is started with
    `raytone-models agent-exec ID` (the Agents page's Launch does): never the whole session, whose
    programs would keep them after a revert."""
    command = ""

    @property
    def path(self):
        return self.home / ".config/raytone-models/agents" / f"{self.id}.env"

    def variables(self, base_url):
        raise NotImplementedError

    def connect(self, *, base_url=ROUTER):
        values = self.variables(base_url)
        if any(not re.fullmatch(r"[A-Za-z0-9._:/@+-]+", str(v)) for v in values.values()):
            raise AgentError("a value this adapter would write is not a plain word")
        mode = 0o600
        self._save_original()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = f"# Raytone Models: {self.id} on the local router, started with raytone-models agent-exec {self.id}\n"
        text += "".join(f"{k}={v}\n" for k, v in values.items())
        _atomic_write(self.path, text.encode(), mode)

    def env(self):
        """The variables in effect when connected (for launching it right away), else {}."""
        if not (self.state / "original.json").exists() or not self.path.exists():
            return {}
        # our own format only: KEY=VALUE lines as connect() writes them
        return dict(l.split("=", 1) for l in self.path.read_text().splitlines() if re.fullmatch(r"[A-Z][A-Z0-9_]*=\S+", l))


class Copilot(EnvAdapter):
    """GitHub Copilot CLI's BYOK variables, offline: it talks to the router only."""
    id, command = "copilot", "copilot"

    def variables(self, base_url):
        return {"COPILOT_PROVIDER_TYPE": "openai", "COPILOT_PROVIDER_BASE_URL": base_url, "COPILOT_MODEL": MODEL,
                "COPILOT_OFFLINE": "true"}


ADAPTERS = {a.id: a for a in (Opencode, Claude, Crush, Pi, Omp, Hermes, Codex, Copilot)}


def get(agent_id, **kw):
    try:
        return ADAPTERS[agent_id](**kw)
    except KeyError:
        raise AgentError(f"no adapter for {agent_id}") from None
