"""scripts/build-engine: builds an engine image on this machine and records its image ID in the
local engines file, next to what is already there."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ID = "sha256:" + "1c" * 32


class BuildEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.log, self.engines = t / "docker.log", t / "engines.json"
        fake = t / "docker"
        fake.write_text(f"""#!/bin/bash
echo "$@" >> {self.log}
# build --iidfile FILE ...: the ID of this build, as docker writes it
while [ $# -gt 0 ]; do [ "$1" = --iidfile ] && echo -n {ID} > "$2"; shift; done
""")
        fake.chmod(0o755)
        self.env = dict(os.environ, RAYTONE_DOCKER=str(fake), RAYTONE_SUDO="", RAYTONE_ENGINES_FILE=str(self.engines))

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args):
        return subprocess.run([str(ROOT / "scripts" / "build-engine"), *args], env=self.env, capture_output=True, text=True)

    def test_builds_and_records_the_image_id(self):
        self.engines.write_text(json.dumps({"llamacpp": {"image": "raytone/llama.cpp@sha256:" + "0" * 64}}))
        r = self.run_script("comfyui")
        self.assertEqual(r.returncode, 0, r.stderr)
        log = self.log.read_text()
        self.assertIn(f"-t raytone/comfyui:local {ROOT}/engines/comfyui", log)
        # From Codex's review of PR #5: the ID comes from this build, not from the shared tag
        self.assertIn("--iidfile", log)
        self.assertNotIn("image inspect", log)
        d = json.loads(self.engines.read_text())
        self.assertEqual(d["comfyui"]["image"], f"raytone/comfyui@{ID}")
        self.assertIn("built", d["comfyui"])
        self.assertIn("llamacpp", d)                  # other engines stay

    def test_an_unknown_engine_is_refused(self):
        r = self.run_script("../../etc")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
