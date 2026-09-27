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
        self.chowned = []
        self.paths = dict(store=self.store, run_dir=self.run, cache=self.cache, systemctl=self.calls.append,
                          engine_user=lambda: ((961, 961), (983, 987)),
                          chown=lambda p, uid, gid: self.chowned.append((pathlib.Path(p).name, uid, gid)))

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
        # the cache is the engine user's alone
        self.assertEqual(self.chowned, [("qwen38-27b", 961, 961)])
        self.assertEqual(stat.S_IMODE((self.cache / "qwen38-27b").stat().st_mode), 0o700)

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

    def test_restarting_an_instance_stops_the_old_one_first(self):
        # From Codex's PR review: `systemctl start` on a running unit does nothing, so a new port in
        # the registry would point the router at nobody
        self.start()
        self.start(port=18005)
        self.assertEqual(self.calls[-2:], [["stop", "raytone-engine@qwen38-27b.service"],
                                           ["start", "raytone-engine@qwen38-27b.service"]])
        self.assertEqual(json.loads((self.run / "instances" / "qwen38-27b.json").read_text())["port"], 18005)

    def test_a_failed_start_is_unregistered(self):
        def failing(args):
            if args[0] == "start":
                raise helper.subprocess.CalledProcessError(1, ["systemctl", *args])
        with self.assertRaises(helper.HelperError):
            helper.start(json.dumps(good()), **{**self.paths, "systemctl": failing})
        self.assertFalse((self.run / "instances" / "qwen38-27b.json").exists())

    def test_the_unit_unregisters_when_it_ends(self):
        self.start()
        helper.unregister("qwen38-27b", **self.paths)
        self.assertFalse((self.run / "instances" / "qwen38-27b.json").exists())

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

    def lstat_of(self, tree):
        """A fake lstat over {path: (is_dir, is_link, uid, mode)}."""
        def lstat(p):
            if p not in tree:
                raise FileNotFoundError(p)
            is_dir, is_link, uid, mode = tree[p]
            kind = stat.S_IFLNK if is_link else (stat.S_IFDIR if is_dir else stat.S_IFREG)
            return os.stat_result((kind | mode, 0, 0, 0, uid, 0, 0, 0, 0, 0))
        return lstat

    def test_the_store_is_a_path_the_user_cannot_swap(self):
        # From Codex's review: the path is checked and then handed to docker, so it must not be
        # replaceable in between: root-owned, not group/other-writable, from / down, no links.
        good_tree = {"/": (1, 0, 0, 0o755), "/var": (1, 0, 0, 0o755), "/var/lib": (1, 0, 0, 0o755),
                     "/var/lib/raytone-models": (1, 0, 0, 0o755), "/var/lib/raytone-models/hf": (1, 0, 0, 0o755)}
        self.assertEqual(helper.check_store("/var/lib/raytone-models/hf", lstat=self.lstat_of(good_tree)),
                         pathlib.Path("/var/lib/raytone-models/hf"))
        bad = {
            "user-owned store": {**good_tree, "/var/lib/raytone-models/hf": (1, 0, 1000, 0o755)},
            "group-writable parent": {**good_tree, "/var/lib/raytone-models": (1, 0, 0, 0o775)},
            "a link on the way": {**good_tree, "/var/lib": (1, 1, 0, 0o777)},
        }
        for name, tree in bad.items():
            with self.subTest(name), self.assertRaises(helper.HelperError):
                helper.check_store("/var/lib/raytone-models/hf", lstat=self.lstat_of(tree))
        for path in ("/home/nvidia/.local/share/raytone/hf", "/", "/var/lib/raytone-models", "/var/lib/raytone-models/../x",
                     "relative/hf"):
            with self.subTest(path), self.assertRaises(helper.HelperError):
                helper.check_store(path, lstat=self.lstat_of(good_tree))

    def test_the_cli_reads_the_spec_from_stdin(self):
        # pkexec passes no environment and arguments are visible in ps: the spec comes on stdin
        self.assertEqual(helper.parse_args(["start"]).command, "start")
        with self.assertRaises(SystemExit):
            helper.parse_args(["start", "--store", "/"])


if __name__ == "__main__":
    unittest.main()
