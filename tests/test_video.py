"""Video generation: MiniMax H3's text-to-video workflow in ComfyUI's API format, queued on the
ComfyUI instance, polled until it finishes, and the video fetched into the user's folder. Tested
against a local fake of ComfyUI's HTTP API."""
import http.server
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.parse

from raytone_models import video


class FakeComfy(http.server.ThreadingHTTPServer):
    def __init__(self):
        self.prompts = []
        self.polls = 0
        self.fail = None          # node_errors to answer /prompt with
        self.error = None         # an execution error to report in the history
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, status, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/prompt":
                    if outer.fail:
                        return self.send(400, {"error": {"message": "Prompt outputs failed validation"}, "node_errors": outer.fail})
                    outer.prompts.append(body)
                    return self.send(200, {"prompt_id": "p-1", "number": 0})
                self.send(404, {})

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                if u.path == "/history/p-1":
                    outer.polls += 1
                    if outer.polls < 3:
                        return self.send(200, {})
                    if outer.error:
                        return self.send(200, {"p-1": {"status": {"status_str": "error", "completed": False,
                                                                  "messages": [["execution_error", {"exception_message": outer.error}]]},
                                                       "outputs": {}}})
                    return self.send(200, {"p-1": {"status": {"status_str": "success", "completed": True},
                                                   "outputs": {"92": {"images": [{"filename": "MiniMax_H3_00001_.mp4",
                                                                                  "subfolder": "video", "type": "output"}],
                                                                      "animated": [True]}}}})
                if u.path == "/view":
                    q = urllib.parse.parse_qs(u.query)
                    if q == {"filename": ["MiniMax_H3_00001_.mp4"], "subfolder": ["video"], "type": ["output"]}:
                        return self.send(200, b"\x00\x00\x00 ftypmp4", "video/mp4")
                self.send(404, {})

        super().__init__(("127.0.0.1", 0), H)
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()


def nodes(wf, kind):
    return [n for n in wf.values() if n["class_type"] == kind]


class WorkflowTests(unittest.TestCase):
    def test_frames_snap_to_the_17k_plus_5_grid(self):
        self.assertEqual(video.frames(5), 124)       # the template's own default for ~5 s
        self.assertEqual(video.frames(3), 73)
        self.assertEqual(video.frames(0.1), 5)
        for s in (1, 2, 5, 7, 10, 15):
            self.assertEqual((video.frames(s) - 5) % 17, 0)

    def test_turbo_text_to_video(self):
        wf = video.workflow("a red fox in snow", size="480p", seconds=5, seed=7)
        [h3] = nodes(wf, "MiniMaxH3ImageToVideo")
        self.assertEqual((h3["inputs"]["prompt"], h3["inputs"]["width"], h3["inputs"]["height"], h3["inputs"]["length"]),
                         ("a red fox in snow", 864, 480, 124))
        [lora] = nodes(wf, "LoraLoaderModelOnly")
        self.assertEqual(lora["inputs"]["lora_name"], video.FILES["lora"])
        [sched] = nodes(wf, "BasicScheduler")
        self.assertEqual(sched["inputs"]["steps"], 8)
        # the sampler and the scheduler run the LoRA'd model
        lora_id = next(k for k, n in wf.items() if n["class_type"] == "LoraLoaderModelOnly")
        self.assertEqual(sched["inputs"]["model"], [lora_id, 0])
        [guider] = nodes(wf, "BasicGuider")
        self.assertEqual(guider["inputs"]["model"], [lora_id, 0])
        self.assertEqual(nodes(wf, "RandomNoise")[0]["inputs"]["noise_seed"], 7)
        self.assertEqual(nodes(wf, "CreateVideo")[0]["inputs"]["fps"], 24)
        self.assertEqual(len(nodes(wf, "SaveVideo")), 1)

    def test_every_link_points_at_a_node(self):
        wf = video.workflow("x")
        for n in wf.values():
            for v in n["inputs"].values():
                if isinstance(v, list):
                    self.assertIn(v[0], wf)

    def test_without_turbo_the_base_model_runs_20_steps(self):
        wf = video.workflow("x", turbo=False)
        self.assertEqual(nodes(wf, "LoraLoaderModelOnly"), [])
        self.assertEqual(nodes(wf, "BasicScheduler")[0]["inputs"]["steps"], 20)

    def test_bad_requests_are_refused(self):
        for kw in ({"size": "4k"}, {"seconds": 0}, {"seconds": 16}, {"prompt": ""}):
            with self.assertRaises(video.VideoError, msg=kw):
                video.workflow(**{"prompt": "x", **kw})


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.srv = FakeComfy()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "Videos"
        self.lines = []

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def test_queue_poll_and_fetch(self):
        path = video.generate(self.base, video.workflow("a fox"), self.out, poll=0.01, emit=self.lines.append)
        self.assertEqual(self.srv.prompts[0]["prompt"], video.workflow("a fox"))
        self.assertTrue(path.exists() and path.parent == self.out and path.suffix == ".mp4")
        self.assertEqual(path.read_bytes(), b"\x00\x00\x00 ftypmp4")
        self.assertEqual(self.lines[0], {"state": "queued", "prompt_id": "p-1"})
        self.assertEqual(self.lines[-1]["done"], str(path))
        self.assertIn("seconds", self.lines[-1])

    def test_a_workflow_comfyui_refuses_is_an_error(self):
        self.srv.fail = {"127": {"errors": [{"message": "Value not in list", "details": "unet_name: x.safetensors"}]}}
        with self.assertRaises(video.VideoError) as e:
            video.generate(self.base, video.workflow("a fox"), self.out, poll=0.01, emit=self.lines.append)
        self.assertIn("unet_name", str(e.exception))

    def test_an_execution_error_is_reported(self):
        self.srv.error = "CUDA out of memory"
        with self.assertRaises(video.VideoError) as e:
            video.generate(self.base, video.workflow("a fox"), self.out, poll=0.01, emit=self.lines.append)
        self.assertIn("CUDA out of memory", str(e.exception))

    def test_it_gives_up_after_the_timeout(self):
        self.srv.polls = -10**9           # never finishes
        with self.assertRaises(video.VideoError):
            video.generate(self.base, video.workflow("a fox"), self.out, poll=0.01, timeout=0.2, emit=self.lines.append)


if __name__ == "__main__":
    unittest.main()
