"""The router: one loopback endpoint for every agent, forwarding each request to the instance that
serves the requested model. Instances are found in the registry the privileged helper writes."""
import http.client
import http.server
import json
import pathlib
import tempfile
import threading
import unittest

from raytone_models import router


class Upstream(http.server.ThreadingHTTPServer):
    """A fake engine: records requests, answers JSON or streams SSE."""

    def __init__(self):
        self.seen = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.seen.append((self.path, dict(self.headers), json.loads(body)))
                if json.loads(body).get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for i in range(3):
                        chunk = f"data: {{\"i\": {i}}}\n\n".encode()
                        self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                        self.wfile.flush()
                    self.wfile.write(b"0\r\n\r\n")
                    return
                out = json.dumps({"served_by": outer.server_address[1], "path": self.path}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        super().__init__(("127.0.0.1", 0), H)
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = pathlib.Path(self.tmp.name)
        self.a, self.b = Upstream(), Upstream()
        self.register("qwen3.8-27b", self.a)
        self.register("muse-glimmer-30b", self.b)
        self.srv = router.make_server("127.0.0.1", 0, registry=self.reg, ports=range(1024, 65536))
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        for s in (self.srv, self.a, self.b):
            s.shutdown()
            s.server_close()
        self.tmp.cleanup()

    def register(self, name, upstream):
        spec = {"id": name.replace(".", "-"), "served_name": name, "port": upstream.server_address[1], "engine": "vllm"}
        (self.reg / f"{spec['id']}.json").write_text(json.dumps(spec))

    def request(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json", **(headers or {})}
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=h)
        r = c.getresponse()
        return r.status, r.getheader("Content-Type"), r.read()

    def test_models_lists_every_instance(self):
        status, _, body = self.request("GET", "/v1/models")
        self.assertEqual(status, 200)
        ids = sorted(m["id"] for m in json.loads(body)["data"])
        self.assertEqual(ids, ["muse-glimmer-30b", "qwen3.8-27b"])

    def test_requests_go_to_the_instance_serving_the_model(self):
        for path in ("/v1/chat/completions", "/v1/completions", "/v1/embeddings", "/v1/messages", "/v1/responses"):
            with self.subTest(path=path):
                status, _, body = self.request("POST", path, {"model": "muse-glimmer-30b", "messages": []})
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), {"served_by": self.b.server_address[1], "path": path})

    def test_streams_are_relayed(self):
        status, ctype, body = self.request("POST", "/v1/chat/completions", {"model": "qwen3.8-27b", "stream": True})
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "text/event-stream")
        self.assertEqual(body.count(b"data: "), 3)

    def test_agent_credentials_are_not_forwarded(self):
        self.request("POST", "/v1/chat/completions", {"model": "qwen3.8-27b"},
                     {"Authorization": "Bearer dummy", "x-api-key": "dummy", "anthropic-version": "2023-06-01"})
        _, headers, _ = self.a.seen[-1]
        lower = {k.lower(): v for k, v in headers.items()}
        self.assertNotIn("authorization", lower)
        self.assertNotIn("x-api-key", lower)
        self.assertEqual(lower["anthropic-version"], "2023-06-01")

    def test_an_unknown_model_is_a_404_naming_the_served_ones(self):
        status, _, body = self.request("POST", "/v1/chat/completions", {"model": "gpt-5"})
        self.assertEqual(status, 404)
        self.assertIn("qwen3.8-27b", json.loads(body)["error"]["message"])

    def test_without_a_model_the_only_instance_serves(self):
        (self.reg / "muse-glimmer-30b.json").unlink()
        status, _, body = self.request("POST", "/v1/chat/completions", {"messages": []})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["served_by"], self.a.server_address[1])
        # the engine is told which model: the name is filled in (Codex)
        self.assertEqual(self.a.seen[-1][2]["model"], "qwen3.8-27b")

    def test_a_model_that_is_not_a_string_is_a_400(self):
        for bad in ([], {}, 3):
            with self.subTest(model=bad):
                status, _, _ = self.request("POST", "/v1/chat/completions", {"model": bad})
                self.assertEqual(status, 400)

    def test_a_foreign_host_header_is_refused(self):
        # DNS rebinding: a web page cannot use the router through a name that resolves to 127.0.0.1
        status, _, _ = self.request("GET", "/v1/models", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)

    def raw(self, data):
        """Send bytes as they are and read until the router closes the connection."""
        import socket
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        sock.sendall(data)
        out = b""
        try:
            while chunk := sock.recv(65536):
                out += chunk
        except socket.timeout:
            out += b"<timeout: connection left open>"
        sock.close()
        return out

    def test_a_refused_request_closes_the_connection(self):
        # From Codex's review: a second request smuggled in the body of a refused one was served
        inner = json.dumps({"model": "qwen3.8-27b"}).encode()
        smuggled = (b"POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(inner)).encode() + b"\r\n\r\n" + inner)
        outer = (b"POST /v1/chat/completions HTTP/1.1\r\nHost: evil.example\r\nContent-Length: "
                 + str(len(smuggled)).encode() + b"\r\n\r\n" + smuggled)
        out = self.raw(outer)
        self.assertIn(b" 403 ", out.split(b"\r\n")[0])
        self.assertNotIn(b"served_by", out)
        self.assertEqual(self.a.seen, [])

    def test_ambiguous_framing_is_refused(self):
        body = json.dumps({"model": "qwen3.8-27b"}).encode()
        cases = {
            "chunked": b"Transfer-Encoding: chunked\r\n",
            "two lengths": b"Content-Length: 5\r\n",
            "two hosts": b"Host: localhost\r\n",
        }
        for name, extra in cases.items():
            with self.subTest(name):
                out = self.raw(b"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\n" + extra +
                               b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
                self.assertIn(b" 400 ", out.split(b"\r\n")[0])
        self.assertEqual(self.a.seen, [])

    def test_only_known_headers_go_upstream(self):
        self.request("POST", "/v1/chat/completions", {"model": "qwen3.8-27b"},
                     {"Cookie": "session=1", "Proxy-Authorization": "Basic x", "X-Custom": "1", "Accept": "text/event-stream"})
        _, headers, _ = self.a.seen[-1]
        lower = {k.lower() for k in headers}
        for h in ("cookie", "proxy-authorization", "x-custom"):
            self.assertNotIn(h, lower)
        self.assertIn("accept", lower)

    def test_a_slow_client_is_cut_off(self):
        # a request that never finishes its body must not hold a thread forever
        self.srv.request_timeout = 1
        out = self.raw(b"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 100\r\n\r\n{")
        self.assertNotIn(b"<timeout", out)

    def test_only_loopback_binds(self):
        with self.assertRaises(ValueError):
            router.make_server("0.0.0.0", 0, registry=self.reg)

    def test_a_registry_entry_on_a_foreign_port_is_ignored(self):
        (self.reg / "bad.json").write_text(json.dumps({"id": "bad", "served_name": "bad", "port": 22}))
        _, _, body = self.request("GET", "/v1/models")
        self.assertNotIn("bad", [m["id"] for m in json.loads(body)["data"]])


if __name__ == "__main__":
    unittest.main()
