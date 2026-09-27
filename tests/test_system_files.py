"""The files installed outside the package: the helper launcher, the engine unit and polkit."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = "/usr/lib/raytone-models/raytone-models-helper"


class SystemFilesTests(unittest.TestCase):
    def test_the_launcher_is_isolated(self):
        first = (ROOT / "bin/raytone-models-helper").read_text().splitlines()[0]
        self.assertEqual(first, "#!/usr/bin/python3 -I")

    def test_the_unit_runs_the_helper_without_a_shell(self):
        unit = (ROOT / "systemd/raytone-engine@.service").read_text()
        self.assertIn(f"ExecStart={HELPER} run %i", unit)
        self.assertIn("Requires=docker.service", unit)
        self.assertNotRegex(unit, r"(?m)^Exec\w*=.*(/bin/sh|bash|;|\||&&)")

    def test_polkit_allows_the_helper_only(self):
        policy = (ROOT / "polkit/org.raytone.models.policy").read_text()
        self.assertIn(f'<annotate key="org.freedesktop.policykit.exec.path">{HELPER}</annotate>', policy)
        self.assertIn("<allow_any>no</allow_any>", policy)
        rules = (ROOT / "polkit/50-raytone-models.rules").read_text()
        cond = re.search(r"if \((.*)\) \{", rules).group(1)
        for part in ('action.id == "org.raytone.models.manage"', "subject.local", "subject.active",
                     'subject.isInGroup("wheel")'):
            self.assertIn(part, cond)


if __name__ == "__main__":
    unittest.main()
