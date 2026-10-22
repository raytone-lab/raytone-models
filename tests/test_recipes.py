"""Recipes: Raytone AI Lab's tested combinations of models, engines and parameters. A recipe is
applied only when its signature verifies; its components go through the same spec checks as any
instance, and its models must be in the store at the pinned revision."""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import types
import unittest
from unittest import mock

from raytone_models import recipes
from tests.test_spec import DIGEST
from tests.test_store import SHA, put

REPO = "RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead"

# a real key, because a drop-in file now has to hold one ssh-keygen recognises rather than
# a key type with anything behind it. Its private half was thrown away on generation.
REAL_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHJ1JXbaDqpobKyWtp9XpQvOFyxtOouJ5VMXfIUwGOtJ"


def recipe(**over):
    r = {
        "schema": 1,
        "id": "qwen38-27b-coder",
        "title": "Qwen3.8 27B NVFP4 for coding agents",
        "description": "Dense 27B, NVFP4, MTP speculative decoding, 256K context.",
        "platforms": ["thor-t5000"],
        "requires": {"memory_gib": 60, "disk_gib": 30},
        "source": "Parameters from Mia's AI Lab single-Spark recipe, adapted to vLLM on the Thor",
        "components": [{
            "role": "chat",
            "served_name": "qwen3.8-27b",
            "model": {"repo": REPO, "revision": SHA},
            "engine": "vllm",
            "image": f"vllm/vllm-openai@{DIGEST}",
            "args": {"gpu-memory-utilization": 0.6, "max-model-len": 262144, "enable-prefix-caching": True},
            "env": {},
        }],
        "agents": {"default_model": "qwen3.8-27b"},
    }
    r.update(over)
    return r


class SchemaTests(unittest.TestCase):
    def test_a_good_recipe_loads(self):
        r = recipes.load(recipe())
        self.assertEqual((r.id, len(r.components)), ("qwen38-27b-coder", 1))

    def refused(self, why, **over):
        with self.assertRaises(recipes.RecipeError, msg=why):
            recipes.load(recipe(**over))

    def test_a_trailing_newline_is_not_a_match(self):
        c = recipe()["components"][0]
        self.refused("revision", components=[{**c, "model": {"repo": REPO, "revision": SHA + "\n"}}])
        self.refused("id", id="qwen38-27b-coder\n")

    def test_refusals(self):
        c = recipe()["components"][0]
        self.refused("unknown schema", schema=2)
        self.refused("bad id", id="Qwen 27B")
        self.refused("no components", components=[])
        self.refused("a revision that is a branch", components=[{**c, "model": {"repo": REPO, "revision": "main"}}])
        self.refused("an argument the engine does not take", components=[{**c, "args": {"load-format": "pt"}}])
        self.refused("an image that is not pinned", components=[{**c, "image": "vllm/vllm-openai:latest"}])
        self.refused("two components with one name", components=[c, c])
        self.refused("an unknown top-level field", extra=1)
        self.refused("an include pattern leaving the repo", components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": ["../x"]}}])

    def test_components_may_not_share_an_instance(self):
        # "a.b" and "a-b" become the same instance id (Codex)
        c = recipe()["components"][0]
        self.refused("same instance id", components=[{**c, "served_name": "q.1"}, {**c, "served_name": "q-1"}],
                     agents={"default_model": "q.1"})

    def test_malformed_fields_are_refused_not_crashed_on(self):
        c = recipe()["components"][0]
        self.refused("include as a string", components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": "*.json"}}])
        self.refused("requires as a list", requires=[])
        self.refused("platforms as a string", platforms="thor-t5000")
        self.refused("title not a string", title=3)
        self.refused("components not a list", components={"a": 1})

    def test_a_draft_path_hidden_in_a_json_string_is_refused(self):
        c = recipe()["components"][0]
        self.refused("string speculative-config naming a path",
                     components=[{**c, "args": {**c["args"], "speculative-config": '{"method":"dflash","model":"/cache/x"}'}}])

    def test_the_default_model_must_be_a_component(self):
        self.refused("default not served", agents={"default_model": "gpt-5"})


class SignatureTests(unittest.TestCase):
    """ssh-keygen -Y: offline, no extra dependency, on every Omarchy and macOS."""

    def setUp(self):
        if not shutil.which("ssh-keygen"):
            self.skipTest("no ssh-keygen")
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(t / "key")], check=True)
        pub = (t / "key.pub").read_text().split()
        (t / "allowed").write_text(f"{recipes.SIGNER} {pub[0]} {pub[1]}\n")
        self.t = t
        self.file = t / "qwen38-27b-coder.json"
        self.file.write_text(json.dumps(recipe()))
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(t / "key"), "-n", recipes.NAMESPACE, str(self.file)],
                       check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_signed_recipe_verifies(self):
        r = recipes.read(self.file, allowed_signers=self.t / "allowed")
        self.assertEqual(r.id, "qwen38-27b-coder")

    def test_a_changed_recipe_does_not(self):
        d = recipe()
        d["components"][0]["args"]["gpu-memory-utilization"] = 0.95
        self.file.write_text(json.dumps(d))
        with self.assertRaises(recipes.RecipeError):
            recipes.read(self.file, allowed_signers=self.t / "allowed")

    def test_the_bytes_parsed_are_the_bytes_verified(self):
        # From Codex's review: reading the file twice let it change between signature check and
        # parse (A, then signed B, then A again). The file is read once.
        # every read_bytes() sees the unsigned A; only the verifier's own open() sees the signed B
        evil = json.dumps(recipe(id="qwen38-27b-coder", title="evil")).encode()
        from unittest import mock
        with mock.patch.object(pathlib.Path, "read_bytes", lambda p: evil):
            with self.assertRaises(recipes.RecipeError):
                recipes.read(self.file, allowed_signers=self.t / "allowed")

    def test_an_unsigned_recipe_does_not(self):
        pathlib.Path(str(self.file) + ".sig").unlink()
        with self.assertRaises(recipes.RecipeError):
            recipes.read(self.file, allowed_signers=self.t / "allowed")


@unittest.skipUnless(os.name == "posix", "the signers directory is read through O_NOFOLLOW/dir_fd")
class LocalSignerFileTests(unittest.TestCase):
    """What a dropped-in signer file is allowed to be. A problem with one FILE skips that file and
    is reported through `problems`; a problem with the DIRECTORY raises, because that is root's own
    configuration and a directory that cannot be read as root's cannot be believed at all.

    A test cannot create a root-owned file, so the ownership rule is lifted here and checked on its
    own in RootOwnedTests."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.tmp.name) / "signers.d"
        self.d.mkdir()
        self.patch = mock.patch.object(recipes, "_require_root_owned", lambda p, st=None: None)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, text):
        (self.d / name).write_text(text)

    def _read(self):
        """(identities, problems) -- what was trusted, and what was said about the rest."""
        problems = []
        got = recipes.local_signers(self.d, problems)
        return [n for n, _ in got], problems

    def _refuses(self, name, text, note=None):
        self._write(name, text)
        ids, problems = self._read()
        self.assertNotIn(name, ids)
        self.assertEqual(len(problems), 1, problems)
        if note:
            self.assertIn(note, problems[0])
        (self.d / name).unlink()

    def test_a_file_cannot_be_named_after_the_lab(self):
        """The whole point: a drop-in named recipes@raytone.ai would verify and be reported as the
        Lab's own key. It is refused before the file is even opened."""
        self._refuses(recipes.SIGNER, f"{recipes.SIGNER} ssh-ed25519 AAAA", recipes.SIGNER)

    def test_a_file_name_is_an_id(self):
        for bad in ("Thor-2", "thor 2", "thor@host", "thor.2"):
            try:
                (self.d / bad).write_text("x ssh-ed25519 AAAA")
            except OSError:
                continue                        # the filesystem refused it first, which is fine
            ids, problems = self._read()
            self.assertEqual(ids, [], bad)
            self.assertEqual(len(problems), 1, problems)
            (self.d / bad).unlink()

    def test_an_options_field_is_part_of_the_syntax(self):
        """`principal [options] keytype key` -- namespaces= is exactly what a recipe key wants, and
        it is what the installed allowed_signers already uses."""
        self._write("thor-2", 'thor-2 namespaces="raytone-recipe" ' + REAL_KEY + chr(10))
        ids, problems = self._read()
        self.assertEqual((ids, problems), (["thor-2"], []))

    def test_a_key_type_with_no_key_behind_it_is_refused(self):
        # otherwise this reaches ssh-keygen and comes back as "the signature does not verify",
        # which blames the recipe for a malformed key file
        for bad in ("thor-2 ssh-ed25519 not-a-key", "thor-2 ssh-madeup garbage", "thor-2"):
            self._refuses("thor-2", bad + chr(10))

    def test_the_principal_inside_must_match_the_file_name(self):
        self._refuses("thor-2", "somebody-else " + REAL_KEY + chr(10))

    def test_one_key_per_file(self):
        self._refuses("thor-2", "thor-2 " + REAL_KEY + chr(10) + "thor-2 " + REAL_KEY + chr(10))

    def test_a_comment_line_is_not_a_second_record(self):
        self._write("thor-2", "# the key this machine signs recipes with" + chr(10)
                    + "thor-2 " + REAL_KEY + chr(10))
        self.assertEqual(self._read(), (["thor-2"], []))

    def test_an_empty_file_is_refused(self):
        self._refuses("thor-2", "")

    def test_a_symlink_is_refused_rather_than_followed(self):
        real = pathlib.Path(self.tmp.name) / "elsewhere"
        real.write_text("thor-2 " + REAL_KEY + chr(10))
        (self.d / "thor-2").symlink_to(real)
        ids, problems = self._read()
        self.assertEqual(ids, [])
        self.assertEqual(len(problems), 1, problems)

    def test_one_bad_file_does_not_take_the_good_ones_with_it(self):
        """The failure boundary: a single unreadable key is not a reason to stop trusting the
        others, and it should be said once rather than once per recipe."""
        self._write("thor-2", "thor-2 " + REAL_KEY + chr(10))
        self._write("broken", "broken ssh-ed25519 not-a-key" + chr(10))
        ids, problems = self._read()
        self.assertEqual(ids, ["thor-2"])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("broken", problems[0])

    def test_a_well_formed_file_is_accepted_and_returns_its_bytes(self):
        body = "thor-2 " + REAL_KEY + chr(10)
        self._write("thor-2", body)
        got = recipes.local_signers(self.d)
        self.assertEqual([n for n, _ in got], ["thor-2"])
        # the bytes, not the path: whatever verifies later must be what was checked here
        self.assertEqual(got[0][1], body.encode())

    def test_a_dotfile_is_ignored(self):
        self._write("thor-2", "thor-2 " + REAL_KEY + chr(10))
        self._write(".keep", "")
        self.assertEqual(self._read(), (["thor-2"], []))

    def test_no_directory_means_no_local_signers(self):
        self.assertEqual(recipes.local_signers(pathlib.Path(self.tmp.name) / "absent"), [])
        self.assertEqual(recipes.local_signers(None), [])

    def test_a_directory_problem_stops_local_trust_altogether(self):
        """A file is skipped, but the directory is root's own configuration: if it is a symlink, a
        dangling symlink, or not a directory at all, none of what it holds can be believed."""
        t = pathlib.Path(self.tmp.name)
        (t / "plain").write_text("not a directory" + chr(10))
        (t / "linked.d").symlink_to(self.d, target_is_directory=True)
        (t / "dangling.d").symlink_to(t / "nothing", target_is_directory=True)
        for case in ("plain", "linked.d", "dangling.d"):
            with self.assertRaises(recipes.RecipeError, msg=case):
                recipes.local_signers(t / case)


class RootOwnedTests(unittest.TestCase):
    """_require_root_owned on its own. A test process is not root and cannot create a root-owned
    file, so the four branches are driven through an lstat() result rather than a real inode --
    which also covers the two writability branches that a real temp file never reaches."""

    @staticmethod
    def _st(uid, mode):
        return types.SimpleNamespace(st_uid=uid, st_mode=mode)

    def _check(self, uid, mode):
        recipes._require_root_owned(pathlib.PurePath("thor-2"), self._st(uid, mode))

    def test_a_file_someone_else_owns_is_refused(self):
        with self.assertRaises(recipes.RecipeError):
            self._check(1000, stat.S_IFREG | 0o644)

    def test_a_group_writable_file_is_refused(self):
        with self.assertRaises(recipes.RecipeError):
            self._check(0, stat.S_IFREG | 0o664)

    def test_a_world_writable_file_is_refused(self):
        with self.assertRaises(recipes.RecipeError):
            self._check(0, stat.S_IFREG | 0o646)

    def test_root_owned_and_not_writable_by_anyone_else_is_accepted(self):
        self._check(0, stat.S_IFREG | 0o644)

    def test_it_lstats_for_itself_when_the_caller_has_no_stat(self):
        # the no-argument path still works, so callers that have not already stat()ed are covered
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        f = pathlib.Path(tmp.name) / "thor-2"
        f.write_text("thor-2 ssh-ed25519 AAAA" + chr(10))
        if os.name != "posix":
            self.skipTest("file ownership is a posix idea; the code this guards only runs on Linux")
        self.assertNotEqual(f.lstat().st_uid, 0, "run the suite as a normal user, not root")
        with self.assertRaises(recipes.RecipeError):
            recipes._require_root_owned(f)


@unittest.skipUnless(os.name == "posix", "the signers directory is read through O_NOFOLLOW/dir_fd")
class LocalSignerTests(unittest.TestCase):
    """A key this machine added, dropped in under its own name rather than shipped to everyone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = pathlib.Path(self.tmp.name)
        self.t = t
        self.local = t / "signers.d"
        self.local.mkdir()
        for name in ("lab", "thor"):
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(t / name)],
                           check=True, capture_output=True)
        pub = lambda n: (t / f"{n}.pub").read_text().split()
        # what every install receives: the Lab key, under the Lab's identity, and nothing else
        (t / "allowed").write_text("{} {} {}\n".format(recipes.SIGNER, *pub("lab")[:2]))
        # what this machine chose, under its own identity, which is the file's name
        (self.local / "thor-2").write_text("thor-2 {} {}\n".format(*pub("thor")[:2]))
        self.file = t / "qwen38-27b-coder.json"
        self.file.write_text(json.dumps(recipe()))
        # these tests are about which key vouches for a recipe, not about who owns the key file.
        # A test cannot create a root-owned directory, so the ownership rule is lifted here and
        # checked on its own in LocalSignerFileTests.test_ownership_is_required.
        self.owner = mock.patch.object(recipes, "_require_root_owned", lambda p, st=None: None)
        self.owner.start()
        self.addCleanup(self.owner.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _sign(self, key):
        sig = pathlib.Path(str(self.file) + ".sig")
        if sig.exists():
            sig.unlink()
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(self.t / key),
                        "-n", recipes.NAMESPACE, str(self.file)], check=True, capture_output=True)

    def _read(self):
        return recipes.read(self.file, allowed_signers=self.t / "allowed", local_dir=self.local)

    def test_the_lab_key_still_verifies_and_says_it_was_the_lab(self):
        self._sign("lab")
        self.assertEqual(self._read().signed_by, recipes.SIGNER)

    def test_a_dropped_in_key_verifies_under_its_own_name(self):
        """The point of the directory: this recipe is usable on this machine, and it says which key
        vouched for it rather than borrowing the Lab's identity."""
        self._sign("thor")
        self.assertEqual(self._read().signed_by, "thor-2")

    def test_a_dropped_in_key_cannot_sign_as_the_lab(self):
        """It is trusted only for the identity its file names. Were it listed under SIGNER instead,
        nothing would distinguish a recipe this machine signed from one the Lab signed."""
        self._sign("thor")
        with self.assertRaises(recipes.RecipeError):
            recipes.read(self.file, allowed_signers=self.t / "allowed", local_dir=self.t / "nope")

    def test_a_key_in_neither_place_does_not_verify(self):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.t / "rogue")],
                       check=True, capture_output=True)
        self._sign("rogue")
        with self.assertRaises(recipes.RecipeError):
            self._read()

    def test_a_changed_recipe_does_not_verify_under_a_local_key_either(self):
        self._sign("thor")
        d = recipe()
        d["components"][0]["args"]["gpu-memory-utilization"] = 0.95
        self.file.write_text(json.dumps(d))
        with self.assertRaises(recipes.RecipeError):
            self._read()

    def test_load_alone_claims_no_signature(self):
        # load() does not check one, so it must not report one
        self.assertEqual(recipes.load(recipe()).signed_by, "")

    def test_a_missing_directory_is_not_an_error(self):
        self._sign("lab")
        self.assertEqual(recipes.read(self.file, allowed_signers=self.t / "allowed",
                                      local_dir=self.t / "does-not-exist").signed_by, recipes.SIGNER)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hf = pathlib.Path(self.tmp.name) / "hf"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_until_the_pinned_revision_is_here(self):
        r = recipes.load(recipe())
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", REPO, "1" * 40, {"config.json": b"{}"})          # another revision
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        root = put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        # without the revision manifest nothing proves the download is whole (Codex)
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        (root / "trees").mkdir()
        (root / "trees" / f"{SHA}.json").write_text(json.dumps({"files": {"config.json": {"size": 2}}}))
        st = recipes.status(r, self.hf)
        self.assertEqual(st["state"], "ready")
        self.assertEqual(st["components"][0]["snapshot"], f"models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots/{SHA}")

    def test_include_lists_decide_completeness_for_partial_repos(self):
        c = recipe()["components"][0]
        r = recipes.load(recipe(components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": ["a.safetensors", "vae/*"]}}]))
        root = put(self.hf / "hub", REPO, SHA, {"a.safetensors": b"a"})
        # the revision manifest lists far more than the recipe needs: only the recipe's files count,
        # but every one of them (both vae shards, not just one match per pattern)
        (root / "trees").mkdir()
        (root / "trees" / f"{SHA}.json").write_text(json.dumps({"files": {"a.safetensors": {"size": 1},
                                                                         "vae/v1.safetensors": {"size": 1},
                                                                         "vae/v2.safetensors": {"size": 1},
                                                                         "huge.safetensors": {"size": 10**11}}}))
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", REPO, SHA, {"vae/v1.safetensors": b"v"})
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", REPO, SHA, {"vae/v2.safetensors": b"w"})
        self.assertEqual(recipes.status(r, self.hf)["state"], "ready")

    def test_specs_for_apply(self):
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        r = recipes.load(recipe())
        [s] = recipes.specs(r, self.hf, used_ports={18000})
        self.assertEqual((s.id, s.port, s.served_name), ("qwen3-8-27b", 18001, "qwen3.8-27b"))
        # the component's role reaches the instance: on one engine that serves both video and
        # stills, it is the only thing that says which of the two an instance is
        self.assertEqual(s.role, r.components[0].role)
        self.assertTrue(s.role)

    def tree(self, repo, sha, files):
        root = self.hf / "hub" / ("models--" + repo.replace("/", "--"))
        (root / "trees").mkdir(parents=True, exist_ok=True)
        (root / "trees" / f"{sha}.json").write_text(json.dumps({"files": {f: {"size": 2} for f in files}}))

    def draft_recipe(self):
        c = recipe()["components"][0]
        draft = {"repo": "poolside/Laguna-S-2.1-DFlash-NVFP4", "revision": "b" * 40}
        return recipes.load(recipe(components=[{**c, "draft": draft,
                                                "args": {**c["args"], "speculative-config": {"method": "dflash", "num_speculative_tokens": 7}}}]))

    def test_a_draft_model_is_part_of_the_recipe(self):
        # DFlash and other speculative decoders load a second repo: it is pinned and fetched too,
        # and the recipe is ready only when both are here
        r = self.draft_recipe()
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        self.assertEqual(recipes.status(r, self.hf)["state"], "missing")
        put(self.hf / "hub", "poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, {"config.json": b"{}"})
        self.tree("poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, ["config.json"])
        self.assertEqual(recipes.status(r, self.hf)["state"], "ready")
        self.assertEqual(len(recipes.fetch_commands(r)), 2)

    def test_the_draft_path_is_filled_into_the_speculative_config(self):
        r = self.draft_recipe()
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        put(self.hf / "hub", "poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        self.tree("poolside/Laguna-S-2.1-DFlash-NVFP4", "b" * 40, ["config.json"])
        [s] = recipes.specs(r, self.hf)
        self.assertEqual(s.args["speculative-config"], {"method": "dflash", "num_speculative_tokens": 7,
                         "model": "/hf/hub/models--poolside--Laguna-S-2.1-DFlash-NVFP4/snapshots/" + "b" * 40})

    def test_an_sglang_draft_path_is_filled_into_its_argument(self):
        c = recipe()["components"][0]
        draft = {"repo": "inclusionAI/Ling-3.0-flash-dspark", "revision": "b" * 40}
        r = recipes.load(recipe(components=[{**c, "engine": "sglang", "image": f"nvcr.io/nvidia/sglang@{DIGEST}",
                                             "draft": draft, "args": {"mem-fraction-static": 0.6,
                                                                      "speculative-algorithm": "DSPARK"}}]))
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        put(self.hf / "hub", draft["repo"], "b" * 40, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        self.tree(draft["repo"], "b" * 40, ["config.json"])
        [s] = recipes.specs(r, self.hf)
        path = "/hf/hub/models--inclusionAI--Ling-3.0-flash-dspark/snapshots/" + "b" * 40
        self.assertEqual(s.args["speculative-draft-model-path"], path)
        self.assertNotIn("speculative-config", s.args)
        self.assertEqual(recipes.expected(r, self.hf)[c["served_name"]][2]["speculative-draft-model-path"], path)

    def test_an_sglang_recipe_cannot_name_its_draft_path(self):
        c = recipe()["components"][0]
        path = "/hf/hub/models--inclusionAI--Ling-3.0-flash-dspark/snapshots/" + "b" * 40
        with self.assertRaises(recipes.RecipeError):
            recipes.load(recipe(components=[{**c, "engine": "sglang", "image": f"nvcr.io/nvidia/sglang@{DIGEST}",
                                             "args": {"speculative-draft-model-path": path}}]))

    def h3_recipe(self):
        c = recipe()["components"][0]
        h3 = {"role": "video", "served_name": "minimax-h3", "engine": "comfyui", "image": "raytone/comfyui@local",
              "model": {"repo": "Comfy-Org/MiniMax-H3", "revision": "c" * 40, "include": ["vae/*"]},
              "args": {"gpu-only": True}}
        return recipes.load(recipe(components=[c, h3]))

    def test_a_recipe_can_serve_video_and_images_at_once(self):
        # "image" is its own role rather than a second use of "video" because a
        # recipe can carry both, on the same engine: the Studio trio runs
        # MiniMax H3 for video and Z-Image Turbo for stills.
        c = recipe()["components"][0]
        video = {"role": "video", "served_name": "minimax-h3", "engine": "comfyui",
                 "image": "raytone/comfyui@local",
                 "model": {"repo": "Comfy-Org/MiniMax-H3", "revision": "c" * 40,
                           "include": ["vae/*"]},
                 "args": {"reserve-vram": 54.0}}
        image = {**video, "role": "image", "served_name": "z-image-turbo",
                 "model": {"repo": "Comfy-Org/z_image_turbo", "revision": "d" * 40,
                           "include": ["vae/ae.safetensors"]},
                 "args": {"lowvram": True}}
        r = recipes.load(recipe(components=[c, video, image]))
        self.assertEqual([x.role for x in r.components], ["chat", "video", "image"])
        with self.assertRaises(recipes.RecipeError):
            recipes.load(recipe(components=[c, {**image, "role": "picture"}]))

    def test_a_component_can_cap_its_memory(self):
        c = recipe()["components"][0]
        r = recipes.load(recipe(components=[{**c, "memory_gib": 99}]))
        self.assertEqual(r.components[0].memory_gib, 99)
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        self.assertEqual(recipes.specs(r, self.hf)[0].memory_gib, 99)
        with self.assertRaises(recipes.RecipeError):
            recipes.load(recipe(components=[{**c, "memory_gib": 4}]))

    def test_a_local_vllm_image_is_named_at_local(self):
        c = recipe()["components"][0]
        r = recipes.load(recipe(components=[{**c, "image": "raytone/vllm-flashnext@local"}]))
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        built = {"vllm-flashnext": {"image": "raytone/vllm-flashnext@sha256:" + "e" * 64}}
        self.assertEqual(recipes.specs(r, self.hf, images=built)[0].image, "raytone/vllm-flashnext@sha256:" + "e" * 64)

    def test_a_locally_built_engine_is_named_not_pinned(self):
        # its image ID differs from machine to machine: the recipe names it, the machine's own
        # engines file (scripts/build-engine) pins it
        r = self.h3_recipe()
        self.assertEqual(r.components[1].image, "raytone/comfyui@local")
        with self.assertRaises(recipes.RecipeError):
            c = recipe()["components"][0]
            recipes.load(recipe(components=[{**c, "image": "vllm/vllm-openai@local"}]))

    def test_the_local_image_resolves_from_this_machine(self):
        r = self.h3_recipe()
        put(self.hf / "hub", REPO, SHA, {"config.json": b"{}"})
        self.tree(REPO, SHA, ["config.json"])
        put(self.hf / "hub", "Comfy-Org/MiniMax-H3", "c" * 40, {"vae/v.safetensors": b"v"})
        self.tree("Comfy-Org/MiniMax-H3", "c" * 40, ["vae/v.safetensors", "diffusion_models/big.safetensors"])
        built = {"comfyui": {"image": "raytone/comfyui@sha256:" + "d" * 64}}
        specs = recipes.specs(r, self.hf, images=built)
        self.assertEqual(specs[1].image, "raytone/comfyui@sha256:" + "d" * 64)
        self.assertEqual(recipes.expected(r, self.hf, images=built)["minimax-h3"][0], "raytone/comfyui@sha256:" + "d" * 64)
        with self.assertRaises(recipes.RecipeError) as e:
            recipes.specs(r, self.hf, images={})
        self.assertIn("build-engine comfyui", str(e.exception))

    def test_a_recipe_cannot_name_its_own_draft_path(self):
        c = recipe()["components"][0]
        with self.assertRaises(recipes.RecipeError):
            recipes.load(recipe(components=[{**c, "args": {**c["args"],
                         "speculative-config": {"method": "dflash", "model": "/cache/../etc"}}}]))

    def test_fetch_commands_pin_the_revision(self):
        c = recipe()["components"][0]
        r = recipes.load(recipe(components=[{**c, "model": {"repo": REPO, "revision": SHA, "include": ["a/*"]}}]))
        [cmd] = recipes.fetch_commands(r)
        self.assertEqual(cmd, ["hf", "download", REPO, "--revision", SHA, "--include", "a/*"])


if __name__ == "__main__":
    unittest.main()
