"""Ollama as an engine. It runs as its own system service (127.0.0.1:11434) with its own model
library, and loads a model on first use; Raytone Models lists that library, loads and unloads
models (keep_alive), pulls new ones, and the router routes to the loaded ones by name.
"""
import json
import re
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:11434"
PORT = 11434
# Ollama names: [namespace/]model[:tag], and what the router accepts as a model name
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)?(:[A-Za-z0-9][A-Za-z0-9._-]*)?")


class OllamaError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Ollama is one fixed address: a redirect never takes a request anywhere else
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.URLError(f"Ollama answered with a redirect to {newurl}; refused")


_OPENER = urllib.request.build_opener(_NoRedirect())


def _check(name):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or ".." in name:
        raise OllamaError(f"{name!r} is not an Ollama model name")
    return name


class Ollama:
    def __init__(self, base=BASE, timeout=5):
        self.base, self.timeout = base.rstrip("/"), timeout

    def _call(self, method, path, body=None, timeout=None):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode() if body is not None else None,
                                     {"Content-Type": "application/json"}, method=method)
        return _OPENER.open(req, timeout=timeout or self.timeout)

    def _json(self, path):
        with self._call("GET", path) as r:
            return json.load(r)

    def version(self):
        try:
            return self._json("/api/version").get("version")
        except (OSError, ValueError):
            return None

    def running(self):
        """The models Ollama has in memory: [{name, context}]."""
        try:
            return [{"name": m["name"], "context": m.get("context_length")} for m in self._json("/api/ps").get("models", [])
                    if NAME_RE.fullmatch(str(m.get("name"))) and ".." not in m["name"]]
        except (OSError, ValueError, KeyError, AttributeError):
            return []

    def loaded(self):
        return [m["name"] for m in self.running()]

    def models(self):
        try:
            tags = self._json("/api/tags").get("models", [])
        except (OSError, ValueError) as e:
            raise OllamaError(f"Ollama did not answer: {e}") from None
        loaded = set(self.loaded())
        out = []
        for m in tags:
            name, d = m.get("name"), m.get("details") or {}
            if not isinstance(name, str) or not NAME_RE.fullmatch(name) or ".." in name:
                continue
            out.append({"name": name, "size": m.get("size"), "family": d.get("family"), "parameters": d.get("parameter_size"),
                        "quant": d.get("quantization_level"), "context": d.get("context_length"), "loaded": name in loaded})
        return out

    def _generate(self, name, keep_alive):
        try:
            with self._call("POST", "/api/generate", {"model": _check(name), "keep_alive": keep_alive}, timeout=600) as r:
                r.read()
        except urllib.error.HTTPError as e:
            raise OllamaError(f"Ollama refused {name}: {e.code}") from None
        except OSError as e:
            raise OllamaError(f"Ollama did not answer: {e}") from None

    def load(self, name, keep_alive=-1):
        # resident until unloaded (Stop), rather than Ollama's idle timeout
        self._generate(name, keep_alive)

    def unload(self, name):
        self._generate(name, 0)

    def delete(self, name):
        try:
            with self._call("DELETE", "/api/delete", {"model": _check(name)}) as r:
                r.read()
        except OSError as e:
            raise OllamaError(f"could not delete {name}: {e}") from None

    def pull(self, name, emit=print):
        """JSON lines: {"status", "progress"?} while it pulls, then {"done": true} or {"error"}."""
        try:
            with self._call("POST", "/api/pull", {"model": _check(name), "stream": True}, timeout=3600) as r:
                for raw in r:
                    d = json.loads(raw)
                    if d.get("error"):
                        raise OllamaError(d["error"])
                    line = {"status": d.get("status", "")}
                    if d.get("total"):
                        line["progress"] = round(d.get("completed", 0) / d["total"], 3)
                    emit(line)
        except (OSError, ValueError) as e:
            raise OllamaError(f"Ollama did not answer: {e}") from None
        emit({"done": True})
