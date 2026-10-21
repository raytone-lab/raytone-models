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

    def test_component_memory_caps_fit_the_declared_budget(self):
        """memory_gib on a component becomes `docker --memory`, so the caps are what actually
        bounds a recipe. If every component names one, they have to fit what the recipe asks the
        machine for -- otherwise the number on the Recipes page is not the number enforced."""
        files = sorted((ROOT / "recipes").glob("*.json")) +             sorted((ROOT / "recipes" / "drafts").glob("*.json"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(f.name):
                r = recipes.load(json.loads(f.read_text()))
                caps = [c.memory_gib for c in r.components]
                if not all(isinstance(x, int) for x in caps):
                    self.skipTest(f"{f.name} does not cap every component")
                self.assertLessEqual(
                    sum(caps), r.memory_gib,
                    f"{f.name}: caps sum to {sum(caps)} but it asks for {r.memory_gib}")



if __name__ == "__main__":
    unittest.main()
