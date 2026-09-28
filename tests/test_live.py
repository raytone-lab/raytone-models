"""The live data the app shows: memory of the unified pool, token counters from each engine's
Prometheus metrics, the engines' configuration, and a streamed chat through the router."""
import http.server
import io
import json
import pathlib
import tempfile
import threading
import unittest
from contextlib import redirect_stdout

from raytone_models import live

MEMINFO = "MemTotal:       127535088 kB\nMemFree:         2000000 kB\nMemAvailable:   86523904 kB\n"
METRICS = """# HELP vllm:generation_tokens_total Number of generation tokens processed.
# TYPE vllm:generation_tokens_total counter
vllm:generation_tokens_total{engine="0",model_name="qwen3.8-27b"} 12345.0
vllm:prompt_tokens_total{engine="0",model_name="qwen3.8-27b"} 67890.0
vllm:num_requests_running{engine="0",model_name="qwen3.8-27b"} 2.0
"""


class Engine(http.server.ThreadingHTTPServer):
    def __init__(self):
        outer = self
        self.bodies = []

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                data = METRICS.encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                outer.bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                events = [{"choices": [{"delta": {"content": "Hel"}}]}, {"choices": [{"delta": {"content": "lo"}}]},
                          {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}]
                for e in events:
                    chunk = f"data: {json.dumps(e)}\n\n".encode()
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                chunk = b"data: [DONE]\n\n"
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n0\r\n\r\n")

        super().__init__(("127.0.0.1", 0), H)
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        (t / "meminfo").write_text(MEMINFO)
        self.meminfo = t / "meminfo"
        self.engine = Engine()
        self.port = self.engine.server_address[1]

    def tearDown(self):
        self.engine.shutdown()
        self.engine.server_close()
        self.tmp.cleanup()

    def test_video_sizes_follow_the_fan_curve(self):
        # From Codex's review of PR #12: 768p passed the thermal guard with JetPack's fan curve
        t = pathlib.Path(self.tmp.name)
        conf = t / "nvfancontrol.conf"
        conf.write_text("<FAN 1>\n\tFAN_DEFAULT_PROFILE cool\n")
        self.assertEqual(live.video_sizes(conf), ["480p"])
        conf.write_text("<FAN 1>\n\tFAN_DEFAULT_PROFILE raytone\n")
        self.assertEqual(live.video_sizes(conf), ["480p", "768p"])
        self.assertEqual(live.video_sizes(t / "none.conf"), ["480p", "768p"])   # no nvfancontrol: not a Thor
        # From Codex's re-review: a configuration that is there but cannot be read allows 480p only
        (t / "dangling.conf").symlink_to(t / "removed.conf")
        self.assertEqual(live.video_sizes(t / "dangling.conf"), ["480p"])
        self.assertEqual(live.video_sizes(t), ["480p"])                        # a directory: unreadable
        from unittest import mock
        with mock.patch("os.lstat", side_effect=PermissionError("denied")):
            self.assertEqual(live.video_sizes(conf), ["480p"])                 # cannot tell: 480p

    def test_memory_of_the_unified_pool(self):
        m = live.memory(self.meminfo)
        self.assertEqual((m["total"], m["available"]), (127535088 * 1024, 86523904 * 1024))

    def test_llama_cpp_counters(self):
        text = ("# HELP llamacpp:tokens_predicted_total Number of generation tokens processed.\n"
                "llamacpp:prompt_tokens_total 120\nllamacpp:tokens_predicted_total 345\nllamacpp:requests_processing 1\n")
        global METRICS
        old, METRICS = METRICS, text          # what the fake engine serves at /metrics
        try:
            c = live.counters(f"http://127.0.0.1:{self.port}/metrics")
        finally:
            METRICS = old
        self.assertEqual(c, {"prompt_tokens": 120.0, "generation_tokens": 345.0, "running": 1.0})

    def test_counters_from_prometheus_metrics(self):
        c = live.counters(f"http://127.0.0.1:{self.port}/metrics")
        self.assertEqual(c, {"generation_tokens": 12345.0, "prompt_tokens": 67890.0, "running": 2.0})

    def test_counters_of_an_engine_that_is_not_up(self):
        self.assertIsNone(live.counters("http://127.0.0.1:1/metrics"))

    def test_chat_streams_deltas_then_a_summary(self):
        out = io.StringIO()
        with redirect_stdout(out):
            live.chat(f"http://127.0.0.1:{self.port}", {"model": "qwen3.8-27b", "messages": [{"role": "user", "content": "hi"}]})
        lines = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual([l["delta"] for l in lines if "delta" in l], ["Hel", "lo"])
        self.assertEqual(lines[-1]["done"], True)
        self.assertEqual(lines[-1]["usage"]["completion_tokens"], 2)
        self.assertTrue(self.engine.bodies[-1]["stream"])

    def test_chat_reports_errors_as_a_line(self):
        out = io.StringIO()
        with redirect_stdout(out):
            live.chat("http://127.0.0.1:1", {"model": "x", "messages": []})
        self.assertIn("error", json.loads(out.getvalue().splitlines()[-1]))


if __name__ == "__main__":
    unittest.main()
