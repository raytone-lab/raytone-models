"""A small Hugging Face Hub client over plain HTTP: search, a repo's files at a commit, and the
variants a user can pick. Downloads themselves go through the official `hf` CLI.

The token, when there is one, travels in the Authorization header only (never in a URL or a log).
A mirror (HF_ENDPOINT, e.g. https://hf-mirror.com) must be HTTPS unless it is on loopback.
"""
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ENDPOINT = "https://huggingface.co"
KINDS = {"video": "text-to-video", "image": "text-to-image", "speech": "automatic-speech-recognition"}
QUANT_RE = re.compile(r"(?i)(UD-[A-Z0-9_]+|IQ\d_[A-Z0-9_]+|Q\d_K_(?:XL|[SML])|Q\d_K|Q\d_\d|MXFP4(?:_MOE)?|NVFP4|BF16|F16|F32)")


class HubError(RuntimeError):
    pass


def _loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


class Hub:
    def __init__(self, endpoint=DEFAULT_ENDPOINT, token=None, timeout=20):
        u = urllib.parse.urlsplit(endpoint)
        if u.scheme != "https" and not (u.scheme == "http" and _loopback(u.hostname or "")):
            raise HubError(f"{endpoint}: a Hub endpoint must be https")
        self.endpoint, self.token, self.timeout = endpoint.rstrip("/"), token, timeout

    def _get(self, path, params=None):
        url = self.endpoint + urllib.parse.quote(path) + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        headers = {"Accept": "application/json", "User-Agent": "raytone-models"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise HubError(f"{path}: needs a Hugging Face token with access (gated or private)") from None
            if e.code == 404:
                raise HubError(f"{path}: not found") from None
            raise HubError(f"{path}: the Hub answered {e.code}") from None
        except (OSError, ValueError) as e:
            raise HubError(f"cannot reach {self.endpoint}: {e}") from None

    def search(self, query, kind=None, limit=30):
        params = {"search": query, "sort": "downloads", "direction": "-1", "limit": str(limit),
                  "expand[]": ["downloads", "gated", "pipeline_tag", "library_name", "tags"]}
        if kind in KINDS:
            params["pipeline_tag"] = KINDS[kind]
        rows = self._get("/api/models", params)
        return [{"id": r["id"], "downloads": r.get("downloads", 0), "gated": bool(r.get("gated")),
                 "pipeline": r.get("pipeline_tag") or "", "library": r.get("library_name") or "",
                 "gguf": "gguf" in (r.get("tags") or []) or r.get("library_name") == "gguf"} for r in rows]

    def files(self, repo, revision=None):
        info = self._get(f"/api/models/{repo}", {"expand[]": ["sha", "gated"]})
        sha = revision or info["sha"]
        tree = self._get(f"/api/models/{repo}/tree/{sha}", {"recursive": "1"})
        files = [{"path": f["path"], "size": int(f.get("size", 0)), "sha256": (f.get("lfs") or {}).get("oid")}
                 for f in tree if f.get("type") == "file"]
        return sha, files


def variants(files):
    """What a user picks: one per GGUF quantization (split parts together, projector files with
    each), or the whole repo when it is not GGUF."""
    ggufs = [f for f in files if f["path"].endswith(".gguf")]
    if not ggufs:
        return [{"name": "all files", "include": [], "size": sum(f["size"] for f in files)}]
    projectors = [f for f in ggufs if "mmproj" in f["path"].lower()]
    groups = {}
    for f in ggufs:
        if f in projectors:
            continue
        m = QUANT_RE.search(f["path"].rsplit("/", 1)[-1])
        groups.setdefault(m.group(1).upper() if m else "other", []).append(f)
    out = []
    for name in sorted(groups):
        chosen = sorted(groups[name], key=lambda f: f["path"]) + projectors
        out.append({"name": name, "include": [f["path"] for f in chosen], "size": sum(f["size"] for f in chosen)})
    return out
