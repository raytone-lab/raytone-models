"""The router: one OpenAI- and Anthropic-compatible endpoint on loopback for every agent.

Each request's "model" picks the instance that serves it, from the registry the privileged helper
writes (one JSON per running instance: served_name and port). Requests and streamed responses are
relayed as they come; agent credentials stay here (the engines are local and need none).
Binding is loopback only and the Host header must be loopback too, so a web page cannot reach it
through DNS rebinding.
"""
import http.client
import http.server
import ipaddress
import json
import pathlib

from . import spec as spec_mod

DEFAULT_REGISTRY = pathlib.Path("/run/raytone-models/instances")
DEFAULT_PORT = 8090
MAX_BODY = 64 << 20
FORWARDED_PATHS = ("/v1/chat/completions", "/v1/completions", "/v1/embeddings", "/v1/messages",
                   "/v1/messages/count_tokens", "/v1/responses")
DROP_HEADERS = {"host", "authorization", "x-api-key", "content-length", "connection", "keep-alive",
                "transfer-encoding", "accept-encoding"}
HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "content-length"}


def _loopback(host):
    host = host.strip("[]")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host_header_ok(value):
    if not value:
        return False
    host = value.rsplit(":", 1)[0] if value.count(":") == 1 or value.startswith("[") else value
    return _loopback(host)


def instances(registry, ports):
    """served_name -> port, from the registry files that make sense."""
    out = {}
    for f in sorted(pathlib.Path(registry).glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        name, port = d.get("served_name"), d.get("port")
        if (isinstance(name, str) and spec_mod.NAME_RE.match(name) and isinstance(port, int)
                and not isinstance(port, bool) and port in ports):
            out[name] = port
    return out


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, registry, ports):
        self.registry, self.ports = registry, ports
        super().__init__(addr, handler)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "raytone-models-router"

    def log_message(self, fmt, *args):
        pass

    def _json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message, kind="invalid_request_error"):
        self._json(status, {"error": {"message": message, "type": kind}})

    def _guard(self):
        if not _host_header_ok(self.headers.get("Host", "")):
            self._error(403, "the router answers loopback hosts only")
            return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        if self.path.split("?")[0] in ("/v1/models", "/models"):
            names = instances(self.server.registry, self.server.ports)
            self._json(200, {"object": "list",
                             "data": [{"id": n, "object": "model", "owned_by": "raytone"} for n in sorted(names)]})
        elif self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._error(404, f"no route {self.path}")

    def do_POST(self):
        if not self._guard():
            return
        path = self.path.split("?")[0]
        if path not in FORWARDED_PATHS:
            return self._error(404, f"no route {path}")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._error(400, "bad Content-Length")
        if length <= 0 or length > MAX_BODY:
            return self._error(413 if length > MAX_BODY else 400, "a JSON body up to 64 MiB is required")
        body = self.rfile.read(length)
        try:
            model = json.loads(body).get("model")
        except (ValueError, AttributeError):
            return self._error(400, "the body is not a JSON object")
        served = instances(self.server.registry, self.server.ports)
        if model is None and len(served) == 1:
            model = next(iter(served))
        if model not in served:
            return self._error(404, f"model {model!r} is not running; running: {', '.join(sorted(served)) or 'none'}",
                               "model_not_found")
        self._relay(served[model], body)

    def _relay(self, port, body):
        headers = {k: v for k, v in self.headers.items() if k.lower() not in DROP_HEADERS}
        headers["Content-Length"] = str(len(body))
        up = http.client.HTTPConnection("127.0.0.1", port, timeout=3600)
        try:
            up.request("POST", self.path, body=body, headers=headers)
            resp = up.getresponse()
        except OSError as e:
            return self._error(502, f"the engine did not answer: {e}", "upstream_error")
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in HOP_HEADERS:
                self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        while True:
            chunk = resp.read1(65536)
            if not chunk:
                break
            self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")
        up.close()


def make_server(host="127.0.0.1", port=DEFAULT_PORT, *, registry=DEFAULT_REGISTRY, ports=spec_mod.INSTANCE_PORTS):
    if not _loopback(host):
        raise ValueError("the router binds loopback only")
    return Server((host, port), Handler, registry, ports)
