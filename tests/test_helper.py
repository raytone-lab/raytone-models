"""The privileged helper: the only code that runs as root. It registers an instance from a spec,
starts and stops its systemd unit, and (as the unit's ExecStart) builds the confined docker run.
Paths are parameters here; the installed entry point fixes them."""
import json
import os
import pathlib
import stat
import tempfile
import unittest

from raytone_models import helper
from tests.test_spec import SNAPSHOT, good


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.store, self.run, self.cache = t / "hf", t / "run", t / "cache"
        (self.store / "hub" / SNAPSHOT).mkdir(parents=True)
        self.calls = []
        self.paths = dict(store=self.store, run_dir=self.run, cache=self.cache, systemctl=self.calls.append)

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, **over):
        return helper.start(json.dumps(good(**over)), **self.paths)

    def test_start_registers_and_starts_the_unit(self):
        self.start()
        entry = self.run / "instances" / "qwen38-27b.json"
        self.assertEqual(json.loads(entry.read_text())["served_name"], "qwen3.8-27b")
        self.assertEqual(stat.S_IMODE(entry.stat().st_mode), 0o644)
        self.assertEqual(self.calls, [["start", "raytone-engine@qwen38-27b.service"]])
        self.assertTrue((self.cache / "qwen38-27b").is_dir())

    def test_a_bad_spec_changes_nothing(self):
        with self.assertRaises(helper.HelperError):
            self.start(image="vllm/vllm-openai:latest")
        self.assertFalse((self.run / "instances").exists() and any((self.run / "instances").iterdir()))
        self.assertEqual(self.calls, [])

    def test_the_model_must_be_in_the_store(self):
        with self.assertRaises(helper.HelperError):
            self.start(model="models--x--y/snapshots/" + "1" * 40)

    def test_a_snapshot_linked_out_of_the_store_is_refused(self):
        outside = pathlib.Path(self.tmp.name) / "elsewhere"
        outside.mkdir()
        link = self.store / "hub" / "models--x--y" / "snapshots" / ("2" * 40)
        link.parent.mkdir(parents=True)
        link.symlink_to(outside)
        with self.assertRaises(helper.HelperError):
            self.start(model="models--x--y/snapshots/" + "2" * 40)

    def test_ports_and_names_do_not_collide(self):
        self.start()
        with self.assertRaises(helper.HelperError):
            self.start(id="other", served_name="other")          # same port
        with self.assertRaises(helper.HelperError):
            self.start(id="other", port=18002)                   # same served name
        self.start(id="qwen38-27b", port=18003)                 # the same instance may be restarted
        self.assertEqual(self.calls[-1], ["start", "raytone-engine@qwen38-27b.service"])

    def test_stop_stops_and_unregisters(self):
        self.start()
        helper.stop("qwen38-27b", **self.paths)
        self.assertEqual(self.calls[-1], ["stop", "raytone-engine@qwen38-27b.service"])
        self.assertFalse((self.run / "instances" / "qwen38-27b.json").exists())

    def test_stop_refuses_a_bad_id(self):
        with self.assertRaises(helper.HelperError):
            helper.stop("../../etc/passwd", **self.paths)

    def test_run_builds_the_argv_from_the_registered_spec_only(self):
        self.start()
        argv = helper.run_argv("qwen38-27b", **self.paths)
        self.assertEqual(argv[:3], ["docker", "run", "--rm"])
        self.assertIn(f"--volume={self.store}:/hf:ro", argv)
        # a registry entry edited behind the helper's back is validated again
        entry = self.run / "instances" / "qwen38-27b.json"
        d = json.loads(entry.read_text())
        d["image"] = "evil.example/x@sha256:" + "b" * 64
        entry.write_text(json.dumps(d))
        with self.assertRaises(helper.HelperError):
            helper.run_argv("qwen38-27b", **self.paths)

    def test_the_cli_reads_the_spec_from_stdin(self):
        # pkexec passes no environment and arguments are visible in ps: the spec comes on stdin
        self.assertEqual(helper.parse_args(["start"]).command, "start")
        with self.assertRaises(SystemExit):
            helper.parse_args(["start", "--store", "/"])


if __name__ == "__main__":
    unittest.main()
