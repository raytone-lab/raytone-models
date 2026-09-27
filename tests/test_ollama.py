"""Ollama as an engine: it runs as its own system service with its own library, loading a model on
first use. Raytone Models lists that library, loads and unloads models, pulls new ones, and routes
to the loaded ones. Tested against a local fake of Ollama's HTTP API."""
import http.server
import json
import threading
import unittest

from raytone_models import ollama

TAGS = {"models": [
    {"name": "qwen3:1.7b", "size": 1359293444, "details": {"family": "qwen3", "parameter_size": "2.0B",
                                                          "quantization_level": "Q4_K_M", "context_length": 40960}},
    {"name": "bad name/../x", "size": 1, "details": {}}]}
PS = {"models": [{"name": "qwen3:1.7b", "size_vram": 1500000000, "context_length": 4096}]}


class FakeOllama(http.server.ThreadingHTTPServer):
    def __init__(self):
        self.posts = []
        self.redirect = None
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, status, body):
                data = json.dumps(body).encode() if not isinstance(body, bytes) else body
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/tags" and outer.redirect:
                    self.send_response(302)
                    self.send_header("Location", outer.redirect)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path == "/api/version":
                    return self.send(200, {"version": "0.34.4"})
                if self.path == "/api/tags":
                    return self.send(200, TAGS)
                if self.path == "/api/ps":
                    return self.send(200, PS)
                self.send(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0) or 2) or b"{}")
                outer.posts.append((self.path, body))
                if self.path == "/api/pull":
                    lines = b"".join(json.dumps(x).encode() + b"\n" for x in (
                        {"status": "pulling manifest"}, {"status": "pulling abc", "total": 100, "completed": 40},
                        {"status": "pulling abc", "total": 100, "completed": 100}, {"status": "success"}))
                    return self.send(200, lines)
                if self.path == "/api/generate":
                    return self.send(200, {"done": True})
                self.send(404, {})

            def do_DELETE(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.posts.append(("DELETE " + self.path, body))
                self.send(200, {})

        super().__init__(("127.0.0.1", 0), H)
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.srv = FakeOllama()
        self.o = ollama.Ollama(f"http://127.0.0.1:{self.srv.server_address[1]}")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_version(self):
        self.assertEqual(self.o.version(), "0.34.4")
        self.assertIsNone(ollama.Ollama("http://127.0.0.1:1").version())

    def test_models_with_what_is_loaded(self):
        [m] = self.o.models()                 # a name the router could not route is left out
        self.assertEqual((m["name"], m["quant"], m["context"], m["loaded"]), ("qwen3:1.7b", "Q4_K_M", 40960, True))

    def test_loaded(self):
        self.assertEqual(self.o.loaded(), ["qwen3:1.7b"])
        self.assertEqual(ollama.Ollama("http://127.0.0.1:1").loaded(), [])

    def test_load_and_unload(self):
        self.o.load("qwen3:1.7b")
        self.o.unload("qwen3:1.7b")
        self.assertEqual(self.srv.posts, [("/api/generate", {"model": "qwen3:1.7b", "keep_alive": -1}),
                                          ("/api/generate", {"model": "qwen3:1.7b", "keep_alive": 0})])

    def test_pull_streams_progress(self):
        lines = []
        self.o.pull("qwen3:4b", emit=lines.append)
        self.assertEqual(self.srv.posts, [("/api/pull", {"model": "qwen3:4b", "stream": True})])
        self.assertEqual(lines[1], {"status": "pulling abc", "progress": 0.4})
        self.assertEqual(lines[-1], {"done": True})

    def test_delete(self):
        self.o.delete("qwen3:1.7b")
        self.assertEqual(self.srv.posts, [("DELETE /api/delete", {"model": "qwen3:1.7b"})])

    def test_a_redirect_is_not_followed(self):
        # From Codex's review of PR #9: the router asks Ollama for its models; a redirect must not
        # take that request to another service
        other = FakeOllama()
        self.addCleanup(other.server_close)
        self.addCleanup(other.shutdown)
        self.srv.redirect = f"http://127.0.0.1:{other.server_address[1]}/api/tags"
        with self.assertRaises(ollama.OllamaError):
            self.o.models()
        self.assertEqual(other.posts, [])
        self.assertEqual(self.o.version(), "0.34.4")        # the other calls still work

    def test_names_are_checked(self):
        for bad in ("../x", "a b", "", "-x", "x\n"):
            with self.assertRaises(ollama.OllamaError, msg=bad):
                self.o.load(bad)
        self.assertEqual(self.srv.posts, [])


if __name__ == "__main__":
    unittest.main()
