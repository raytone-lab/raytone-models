"""The Hugging Face client: search, a repo's files at a commit, and the variants a user can pick
(GGUF quantizations, or the whole repo). Tested against a local fake of the Hub's HTTP API."""
import http.server
import json
import threading
import unittest
import urllib.parse

from raytone_models import hf

SHA = "a" * 40


class FakeHub(http.server.ThreadingHTTPServer):
    def __init__(self):
        self.seen = []
        self.redirect_to = None     # an absolute URL /api/models/moved/away redirects to
        self.next_link = None       # overrides the tree's next-page link
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.seen.append((self.path, self.headers.get("Authorization")))
                u = urllib.parse.urlsplit(self.path)
                q = urllib.parse.parse_qs(u.query)
                origin = f"http://127.0.0.1:{outer.server_address[1]}"
                if u.path == "/api/models/moved/away":
                    self.send_response(302)
                    self.send_header("Location", outer.redirect_to)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if u.path == "/api/models/renamed/repo":
                    self.send_response(307)
                    self.send_header("Location", origin + "/api/models/unsloth/Qwen3.8-27B-GGUF")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                link = None
                if u.path == "/api/models":
                    body = [{"id": "unsloth/Qwen3.8-27B-GGUF", "downloads": 900, "gated": False,
                             "pipeline_tag": "image-text-to-text", "library_name": "gguf", "tags": ["gguf"]},
                            {"id": "meta/secret", "downloads": 5, "gated": "manual", "pipeline_tag": "text-generation"}]
                    if q.get("search") == ["nothing"]:
                        body = []
                elif u.path in ("/api/models/unsloth/Qwen3.8-27B-GGUF", "/api/models/unsloth/Qwen3.8-27B-GGUF/revision/main"):
                    body = {"id": "unsloth/Qwen3.8-27B-GGUF", "sha": SHA, "gated": False}
                elif u.path == "/api/models/big/GGUF":
                    body = {"id": "big/GGUF", "sha": SHA}
                elif u.path == f"/api/models/big/GGUF/tree/{SHA}":
                    # the tree API pages with a Link header, like the Hub does for large repos
                    if q.get("cursor") == ["2"]:
                        body = [{"type": "file", "path": "Q8_0/big-Q8_0-00002-of-00002.gguf", "size": 7, "lfs": {"oid": "6" * 64}}]
                    else:
                        body = [{"type": "file", "path": "Q8_0/big-Q8_0-00001-of-00002.gguf", "size": 5, "lfs": {"oid": "5" * 64}}]
                        link = f'<{outer.next_link or origin + u.path + "?recursive=1&cursor=2"}>; rel="next"'
                elif u.path == "/api/models/short/rev/revision/abc123":
                    body = {"id": "short/rev", "sha": "abc123"}
                elif u.path == f"/api/models/unsloth/Qwen3.8-27B-GGUF/tree/{SHA}":
                    body = [{"type": "file", "path": "README.md", "size": 10},
                            {"type": "file", "path": "Qwen3.8-27B-Q4_K_M.gguf", "size": 16_000, "lfs": {"oid": "1" * 64}},
                            {"type": "file", "path": "Q8_0/Qwen3.8-27B-Q8_0-00001-of-00002.gguf", "size": 15_000, "lfs": {"oid": "2" * 64}},
                            {"type": "file", "path": "Q8_0/Qwen3.8-27B-Q8_0-00002-of-00002.gguf", "size": 14_000, "lfs": {"oid": "3" * 64}},
                            {"type": "file", "path": "mmproj-F16.gguf", "size": 900, "lfs": {"oid": "4" * 64}},
                            {"type": "directory", "path": "Q8_0"}]
                elif u.path == "/api/models/nobody/nothing":
                    self.send_response(404)
                    self.end_headers()
                    return
                else:
                    self.send_response(500)
                    self.end_headers()
                    return
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                if link:
                    self.send_header("Link", link)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        super().__init__(("127.0.0.1", 0), H)
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()


class HubTests(unittest.TestCase):
    def setUp(self):
        self.hub = FakeHub()
        self.c = hf.Hub(endpoint=f"http://127.0.0.1:{self.hub.server_address[1]}", token=None)

    def tearDown(self):
        self.hub.shutdown()
        self.hub.server_close()

    def test_search_returns_rows_and_marks_gated_repos(self):
        rows = self.c.search("qwen3.8")
        self.assertEqual([r["id"] for r in rows], ["unsloth/Qwen3.8-27B-GGUF", "meta/secret"])
        self.assertEqual([r["gated"] for r in rows], [False, True])
        path = urllib.parse.urlsplit(self.hub.seen[-1][0])
        q = urllib.parse.parse_qs(path.query)
        self.assertEqual((q["search"], q["sort"]), (["qwen3.8"], ["downloads"]))

    def test_search_by_kind(self):
        self.c.search("wan", kind="video")
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.hub.seen[-1][0]).query)
        self.assertEqual(q["pipeline_tag"], ["text-to-video"])

    def test_files_at_the_current_commit(self):
        sha, files = self.c.files("unsloth/Qwen3.8-27B-GGUF")
        self.assertEqual(sha, SHA)
        self.assertEqual(len(files), 5)
        self.assertEqual(files[1], {"path": "Qwen3.8-27B-Q4_K_M.gguf", "size": 16_000, "sha256": "1" * 64})

    def test_gguf_variants_group_split_files_and_keep_the_projector(self):
        _, files = self.c.files("unsloth/Qwen3.8-27B-GGUF")
        v = {x["name"]: x for x in hf.variants(files)}
        self.assertEqual(sorted(v), ["Q4_K_M", "Q8_0"])
        self.assertEqual(v["Q8_0"]["include"], ["Q8_0/Qwen3.8-27B-Q8_0-00001-of-00002.gguf",
                                                "Q8_0/Qwen3.8-27B-Q8_0-00002-of-00002.gguf", "mmproj-F16.gguf"])
        self.assertEqual(v["Q8_0"]["size"], 15_000 + 14_000 + 900)

    def test_a_safetensors_repo_is_one_variant(self):
        files = [{"path": "config.json", "size": 1, "sha256": None},
                 {"path": "model-00001-of-00002.safetensors", "size": 5, "sha256": "x"}]
        self.assertEqual(hf.variants(files), [{"name": "all files", "include": [], "size": 6}])

    def test_the_token_goes_in_the_header_only(self):
        c = hf.Hub(endpoint=self.c.endpoint, token="hf_secret")
        c.search("qwen")
        path, auth = self.hub.seen[-1]
        self.assertEqual(auth, "Bearer hf_secret")
        self.assertNotIn("hf_secret", path)

    def test_a_missing_repo_is_a_clear_error(self):
        with self.assertRaises(hf.HubError):
            self.c.files("nobody/nothing")

    def test_a_redirect_to_another_origin_is_refused_and_never_sees_the_token(self):
        # From Codex's review: urllib follows redirects and would carry the Authorization header to
        # whatever host a mirror names, even over plain HTTP.
        other = FakeHub()
        self.addCleanup(other.server_close)
        self.addCleanup(other.shutdown)
        self.hub.redirect_to = f"http://127.0.0.1:{other.server_address[1]}/api/models/unsloth/Qwen3.8-27B-GGUF"
        c = hf.Hub(endpoint=self.c.endpoint, token="hf_secret")
        with self.assertRaises(hf.HubError):
            c.files("moved/away")
        self.assertEqual(other.seen, [])

    def test_a_redirect_within_the_hub_is_followed(self):
        # the Hub redirects a renamed repo to its new name on the same host
        sha, files = self.c.files("renamed/repo")
        self.assertEqual((sha, len(files)), (SHA, 5))

    def test_the_file_tree_is_read_page_by_page(self):
        sha, files = self.c.files("big/GGUF")
        self.assertEqual([f["path"] for f in files], ["Q8_0/big-Q8_0-00001-of-00002.gguf", "Q8_0/big-Q8_0-00002-of-00002.gguf"])
        self.assertEqual(hf.variants(files)[0]["size"], 12)

    def test_a_next_page_on_another_origin_is_refused(self):
        self.hub.next_link = "https://evil.example/api/models/big/GGUF/tree/x"
        with self.assertRaises(hf.HubError):
            self.c.files("big/GGUF")

    def test_a_branch_or_tag_resolves_to_its_commit(self):
        # `download org/model@main` must pin the commit hf will cache under, not the name "main"
        sha, _ = self.c.files("unsloth/Qwen3.8-27B-GGUF", "main")
        self.assertEqual(sha, SHA)
        with self.assertRaises(hf.HubError):
            self.c.files("short/rev", "abc123")     # the Hub must answer with a full commit

    def test_only_https_endpoints_outside_loopback(self):
        with self.assertRaises(hf.HubError):
            hf.Hub(endpoint="http://hf-mirror.com")
        hf.Hub(endpoint="https://hf-mirror.com")


if __name__ == "__main__":
    unittest.main()
