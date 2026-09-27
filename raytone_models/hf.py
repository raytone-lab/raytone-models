"""A small Hugging Face Hub client over plain HTTP: search, a repo's files at a commit, and the
variants a user can pick. Downloads themselves go through the official `hf` CLI.

The token, when there is one, travels in the Authorization header only (never in a URL or a log).
A mirror (HF_ENDPOINT, e.g. https://hf-mirror.com) must be HTTPS unless it is on loopback, and
every request stays on its origin: redirects and next-page links elsewhere are refused, so the
token never reaches another host.
"""
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ENDPOINT = "https://huggingface.co"
KINDS = {"video": "text-to-video", "image": "text-to-image", "speech": "automatic-speech-recognition"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LINK_NEXT_RE = re.compile(r'<([^>]+)>\s*;\s*rel="?next"?')
QUANT_RE = re.compile(r"(?i)(UD-[A-Z0-9_]+|IQ\d_[A-Z0-9_]+|Q\d_K_(?:XL|[SML])|Q\d_K|Q\d_\d|MXFP4(?:_MOE)?|NVFP4|BF16|F16|F32)")


class HubError(RuntimeError):
    pass


def _loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _origin(url):
    u = urllib.parse.urlsplit(url)
    return (u.scheme, (u.hostname or "").lower(), u.port or {"https": 443, "http": 80}.get(u.scheme))


class _SameOrigin(urllib.request.HTTPRedirectHandler):
    def __init__(self, origin):
        self.origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(newurl) != self.origin:
            raise HubError(f"the Hub redirected to another host ({urllib.parse.urlsplit(newurl).hostname}); refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Hub:
    def __init__(self, endpoint=DEFAULT_ENDPOINT, token=None, timeout=20):
        u = urllib.parse.urlsplit(endpoint)
        if u.scheme != "https" and not (u.scheme == "http" and _loopback(u.hostname or "")):
            raise HubError(f"{endpoint}: a Hub endpoint must be https")
        self.endpoint, self.token, self.timeout = endpoint.rstrip("/"), token, timeout
        self.origin = _origin(self.endpoint)
        self.opener = urllib.request.build_opener(_SameOrigin(self.origin))

    def _get(self, path, params=None):
        url = self.endpoint + urllib.parse.quote(path) + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        return self._fetch(url, path)[0]

    def _get_all(self, path, params=None):
        """A listing the Hub pages with Link: <next>; rel="next"."""
        url = self.endpoint + urllib.parse.quote(path) + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        out = []
        while url:
            rows, link = self._fetch(url, path)
            out += rows
            m = LINK_NEXT_RE.search(link or "")
            url = m.group(1) if m else None
            if url and _origin(url) != self.origin:
                raise HubError(f"{path}: the next page is on another host; refused")
        return out

    def _fetch(self, url, path):
        headers = {"Accept": "application/json", "User-Agent": "raytone-models"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with self.opener.open(urllib.request.Request(url, headers=headers), timeout=self.timeout) as r:
                return json.load(r), r.headers.get("Link")
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
        # a branch, tag or short hash resolves to the full commit hf caches the snapshot under
        path = f"/api/models/{repo}" + (f"/revision/{revision}" if revision else "")
        info = self._get(path, {"expand[]": ["sha", "gated"]})
        sha = info.get("sha") if isinstance(info, dict) else None
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            raise HubError(f"{repo}: the Hub did not name a full commit for {revision or 'the main branch'}")
        repo = info.get("id") or repo     # a renamed repo answers under its new name
        tree = self._get_all(f"/api/models/{repo}/tree/{sha}", {"recursive": "1"})
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
