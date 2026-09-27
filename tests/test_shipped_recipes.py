"""The recipes this repository ships: each one is signed by the key in packaging/allowed_signers and
loads; drafts load too (they are signed once they have been checked on the device)."""
import json
import pathlib
import shutil
import unittest

from raytone_models import recipes

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ShippedRecipesTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ssh-keygen"), "no ssh-keygen")
    def test_every_shipped_recipe_is_signed_and_valid(self):
        files = sorted((ROOT / "recipes").glob("*.json"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(f.name):
                r = recipes.read(f, allowed_signers=ROOT / "packaging" / "allowed_signers")
                self.assertEqual(r.id, f.stem)

    def test_drafts_are_valid_recipes(self):
        for f in sorted((ROOT / "recipes" / "drafts").glob("*.json")):
            with self.subTest(f.name):
                self.assertEqual(recipes.load(json.loads(f.read_text())).id, f.stem)


if __name__ == "__main__":
    unittest.main()
