"""A small Hugging Face Hub client over plain HTTP: search, a repo's files at a commit, and the
variants a user can pick. Downloads themselves go through the official `hf` CLI.

The token, when there is one, travels in the Authorization header only (never in a URL or a log).
A mirror (HF_ENDPOINT, e.g. https://hf-mirror.com) must be HTTPS unless it is on loopback, and
every request stays on its origin: redirects and next-page links elsewhere are refused, so the
token never reaches another host.
"""
import ipaddress
import json
import os
import pathlib
import re
import tomllib
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


def validate_endpoint(endpoint):
    try:
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError()
        endpoint = endpoint.strip().rstrip("/")
        u = urllib.parse.urlsplit(endpoint)
        if (not u.hostname or u.username is not None or u.password is not None or u.query or u.fragment
                or any(c.isspace() for c in endpoint)
                or (u.scheme != "https" and not (u.scheme == "http" and _loopback(u.hostname)))):
            raise ValueError()
        _origin(endpoint)
        return endpoint
    except (ValueError, TypeError):
        raise HubError("模型源地址无效：请使用不含账号、密码或查询参数的 HTTPS 地址。") from None


def resolve_endpoint(explicit=None, *, home=None, environ=None):
    """Resolve only for network operations; bad Hub config never blocks local inference."""
    environ = os.environ if environ is None else environ
    if explicit is not None:
        return validate_endpoint(explicit)
    if environ.get("HF_ENDPOINT", "").strip():
        return validate_endpoint(environ["HF_ENDPOINT"])
    path = pathlib.Path(environ.get("RAYTONE_PROVIDER_CONFIG") or
                        pathlib.Path(home or pathlib.Path.home()) / ".config/raytone/provider.toml")
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except FileNotFoundError:
        return DEFAULT_ENDPOINT
    except (OSError, ValueError):
        raise HubError("无法读取模型下载源配置，请检查 provider.toml；本地模型仍可使用。") from None
    section = data.get("downloads", {})
    if not isinstance(section, dict):
        raise HubError("模型下载源配置格式错误，请检查 provider.toml 的 downloads 节。")
    value = section.get("hf_endpoint")
    return DEFAULT_ENDPOINT if value is None or value == "" else validate_endpoint(value)


def download_environment(hf_home, endpoint, token=None):
    env = dict(os.environ, HF_HOME=str(hf_home), HF_ENDPOINT=validate_endpoint(endpoint),
               HF_HUB_DISABLE_TELEMETRY="1")
    env.pop("HF_TOKEN", None)
    if token:
        env["HF_TOKEN"] = token
    return env


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
        self.endpoint, self.token, self.timeout = validate_endpoint(endpoint), token, timeout
        self.origin = _origin(self.endpoint)
        self.opener = urllib.request.build_opener(_SameOrigin(self.origin))
        # The mirror's ordinary response supplies these fields; expand[]
        # currently times out/502s. One request stays within the UI deadline.
        self.expanded_metadata = self.origin != ("https", "hf-mirror.com", 443)

    def _get(self, path, params=None):
        url = self.endpoint + urllib.parse.quote(path) + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        return self._fetch(url, path)[0]

    def _get_all(self, path, params=None):
        """A listing the Hub pages with Link: <next>; rel="next"."""
        url = self.endpoint + urllib.parse.quote(path) + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        out = []
        while url:
            rows, link = self._fetch(url, path)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise HubError("模型源文件清单格式错误，请稍后重试。")
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
                raise HubError("模型源拒绝访问（HTTP %s），请检查访问限制或模型授权。" % e.code) from None
            if e.code == 404:
                raise HubError("模型仓库或版本不存在（HTTP 404）。") from None
            if e.code == 429:
                raise HubError("模型源请求过于频繁（HTTP 429），请稍后重试。") from None
            raise HubError("模型源服务暂不可用（HTTP %s），请稍后重试。" % e.code) from None
        except TimeoutError:
            raise HubError("连接模型源超时，请检查网络或稍后重试。") from None
        except ValueError:
            raise HubError("模型源返回了无效数据，请稍后重试。") from None
        except OSError:
            raise HubError("无法连接模型源，请检查网络、代理和 HTTPS 连接。") from None

    def search(self, query, kind=None, limit=30):
        params = {"search": query, "sort": "downloads", "direction": "-1", "limit": str(limit)}
        if self.expanded_metadata:
            params["expand[]"] = ["downloads", "gated", "pipeline_tag", "library_name", "tags"]
        if kind in KINDS:
            params["pipeline_tag"] = KINDS[kind]
        rows = self._get("/api/models", params)
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get("id"), str) for r in rows):
            raise HubError("模型源搜索结果格式错误，请稍后重试。")
        return [{"id": r["id"], "downloads": r.get("downloads", 0), "gated": bool(r.get("gated")),
                 "pipeline": r.get("pipeline_tag") or "", "library": r.get("library_name") or "",
                 "gguf": "gguf" in (r.get("tags") or []) or r.get("library_name") == "gguf"} for r in rows]

    def files(self, repo, revision=None):
        # a branch, tag or short hash resolves to the full commit hf caches the snapshot under
        path = f"/api/models/{repo}" + (f"/revision/{revision}" if revision else "")
        info = self._get(path, {"expand[]": ["sha", "gated"]} if self.expanded_metadata else None)
        sha = info.get("sha") if isinstance(info, dict) else None
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
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
