"""Downloads: `hf download` in the background, pinned to a commit, with progress measured in the
store (finished files plus the partial blobs being written) against the Hub's file sizes."""
import json
import os
import pathlib
import tempfile
import unittest

from raytone_models import downloads
from tests.test_store import put

SHA = "b" * 40
REPO = "unsloth/Qwen3.8-27B-GGUF"
FILES = [{"path": "Qwen3.8-27B-Q4_K_M.gguf", "size": 100, "sha256": "1" * 64},
         {"path": "mmproj-F16.gguf", "size": 20, "sha256": "4" * 64}]


class FakeProc:
    pid = 4242


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.hf, self.state = t / "hf", t / "state"
        self.spawned = []
        self.alive = {4242}
        self.kw = dict(hf_home=self.hf, state_dir=self.state, alive=lambda pid: pid in self.alive,
                       spawn=lambda argv, env, log: self.spawned.append((argv, env)) or FakeProc())

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, token=None):
        return downloads.start(REPO, SHA, FILES, include=[f["path"] for f in FILES], token=token, **self.kw)

    def test_start_runs_hf_pinned_to_the_commit(self):
        d = self.start()
        [(argv, env)] = self.spawned
        self.assertEqual(argv, ["hf", "download", REPO, "--revision", SHA,
                                "--include", "Qwen3.8-27B-Q4_K_M.gguf", "--include", "mmproj-F16.gguf"])
        self.assertEqual(env["HF_HOME"], str(self.hf))
        self.assertNotIn("HF_TOKEN", env)
        self.assertEqual((d["state"], d["expected"]), ("running", 120))

    def test_the_token_goes_through_the_environment_only(self):
        self.start(token="hf_secret")
        argv, env = self.spawned[0]
        self.assertEqual(env["HF_TOKEN"], "hf_secret")
        self.assertNotIn("hf_secret", " ".join(argv))
        self.assertNotIn("hf_secret", (self.state / f"{downloads.download_id(REPO, SHA, [f['path'] for f in FILES])}.json").read_text())

    def test_progress_counts_finished_files_and_partial_blobs(self):
        d = self.start()
        root = put(self.hf / "hub", REPO, SHA, {"mmproj-F16.gguf": b"p" * 20})
        # huggingface_hub 2 names partial blobs <sha256>.<random>.incomplete (seen on the Thor)
        (root / "blobs" / ("1" * 64 + ".eac5b805.incomplete")).write_bytes(b"x" * 50)
        (root / "blobs" / ("1" * 64 + ".00000000.incomplete")).write_bytes(b"x" * 10)
        [row] = downloads.listing(**self.kw)
        self.assertEqual((row["id"], row["state"], row["done"]), (d["id"], "running", 70))
        self.assertAlmostEqual(row["progress"], 70 / 120)

    def test_finished_when_every_file_is_there(self):
        self.start()
        put(self.hf / "hub", REPO, SHA, {"mmproj-F16.gguf": b"p" * 20, "Qwen3.8-27B-Q4_K_M.gguf": b"q" * 100})
        self.alive.clear()
        [row] = downloads.listing(**self.kw)
        self.assertEqual((row["state"], row["progress"]), ("done", 1.0))

    def test_a_process_that_died_early_is_failed(self):
        self.start()
        self.alive.clear()
        [row] = downloads.listing(**self.kw)
        self.assertEqual(row["state"], "failed")

    def test_cancel(self):
        d = self.start()
        killed = []
        downloads.cancel(d["id"], kill=lambda pid: killed.append(pid), **self.kw)
        self.assertEqual(killed, [4242])
        self.alive.clear()
        [row] = downloads.listing(**self.kw)
        self.assertEqual(row["state"], "cancelled")

    def test_a_second_start_of_a_running_download_is_refused(self):
        self.start()
        with self.assertRaises(downloads.DownloadError):
            self.start()

    def test_ids_are_stable_and_safe(self):
        i = downloads.download_id("a/b", SHA, ["x/*"])
        self.assertRegex(i, r"^[a-z0-9-]+$")
        self.assertEqual(i, downloads.download_id("a/b", SHA, ["x/*"]))
        self.assertNotEqual(i, downloads.download_id("a/b", SHA, ["y/*"]))


if __name__ == "__main__":
    unittest.main()
