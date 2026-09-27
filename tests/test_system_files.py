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
        # an engine that exits or fails leaves the registry (and the router, and the panel)
        self.assertIn(f"ExecStopPost={HELPER} unregister %i", unit)
        self.assertNotRegex(unit, r"(?m)^Exec\w*=.*(/bin/sh|bash|;|\||&&)")

    def test_the_app_opens_one_window(self):
        launcher = (ROOT / "bin/raytone-models-app").read_text()
        self.assertIn("pgrep -f", launcher)
        self.assertIn("focuswindow", launcher)
        self.assertIn('exec qs -p "$APP"', launcher)
        desktop = (ROOT / "packaging/raytone-models.desktop").read_text()
        self.assertIn("Exec=raytone-models-app", desktop)
        self.assertIn("Icon=raytone-models", desktop)

    def test_the_package_installs_the_app(self):
        pkg = (ROOT / "packaging/PKGBUILD").read_text()
        for needle in ("usr/share/raytone-models/app", "raytone-models-app", "applications/raytone-models.desktop",
                       "icons/hicolor/scalable/apps/raytone-models.svg", "quickshell", "wl-clipboard"):
            self.assertIn(needle, pkg)
        self.assertNotIn("plugin/raytone.models", pkg)

    def test_the_package_can_build_engines_on_the_device(self):
        pkg = (ROOT / "packaging/PKGBUILD").read_text()
        for needle in ('"$src/engines" "$lib/engines"', "scripts/build-engine", "usr/bin/raytone-models-build-engine"):
            self.assertIn(needle, pkg)
        self.assertTrue((ROOT / "engines/comfyui/Dockerfile").exists())

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
