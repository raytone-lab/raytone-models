"""Recipes: Raytone AI Lab's tested combinations of models, engines and parameters.

A recipe is JSON (schema 1) signed with `ssh-keygen -Y sign -n raytone-recipe`; it is used only
when the signature verifies against the allowed signers shipped with the package. Each component
is one instance: a model at a pinned revision (optionally only some of its files), an engine, a
pinned image, and arguments that pass the same checks as any spec.
"""
import dataclasses
import errno
import fnmatch
import json
import os
import pathlib
import re
import stat
import subprocess
import tempfile

from . import spec as spec_mod, store

NAMESPACE = "raytone-recipe"
SIGNER = "recipes@raytone.ai"
SYSTEM_DIR = pathlib.Path("/usr/share/raytone-models/recipes")
ALLOWED_SIGNERS = pathlib.Path("/usr/share/raytone-models/allowed_signers")
# Keys added on one machine, each in its own file under its own identity. The shipped
# allowed_signers carries the Lab key and nothing else: a key that lives on one device does not
# belong in a file every install receives, because this namespace puts no limit on WHICH recipes a
# trusted key may sign -- it could sign any of them, under the Lab's own identity. Kept here
# instead, the trust stays on the machine that chose it, and survives an upgrade because pacman
# owns the directory but not what is dropped into it.
LOCAL_SIGNERS_DIR = pathlib.Path("/etc/raytone/recipe-allowed-signers.d")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REV_RE = re.compile(r"^[0-9a-f]{40}$")
PATTERN_RE = re.compile(r"^[A-Za-z0-9_.*?/-]{1,200}$")
TOP = {"schema", "id", "title", "description", "platforms", "requires", "source", "components", "agents"}
COMPONENT = {"role", "served_name", "model", "draft", "engine", "image", "args", "env", "memory_gib"}
# "image" is text-to-image. It is a separate role rather than a reuse of "video"
# because a recipe can carry both at once -- the Studio trio runs MiniMax H3 for
# video and Z-Image Turbo for stills -- while the engine behind them is the same
# one, which spec.py already calls "video and image generation".
ROLES = {"chat", "coder", "vision", "video", "image", "embedding", "draft"}


class RecipeError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Component:
    role: str
    served_name: str
    repo: str
    revision: str
    include: tuple
    engine: str
    image: str
    args: dict
    env: dict
    draft_repo: str = None       # a speculative decoder's own weights (DFlash, DSpark drafts)
    draft_revision: str = None
    memory_gib: int = None       # a hard memory limit for its container


@dataclasses.dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    description: str
    platforms: tuple
    memory_gib: int
    disk_gib: int
    source: str
    components: tuple
    default_model: str
    # which key vouched for this file: recipes.SIGNER for the Lab's, otherwise the name of the
    # dropped-in signers file. "" when the recipe was never read from disk (load() alone does not
    # check a signature, so it must not claim one).
    #
    # It is a label for a person, NOT an authorization credential: read() is the only thing that
    # sets it truthfully, and any caller can construct a Recipe with it set to anything. Decide
    # whether to trust a recipe by having gone through read(), never by reading this field.
    signed_by: str = ""

    def to_dict(self):
        return dataclasses.asdict(self)


def _component(c):
    if not isinstance(c, dict) or set(c) - COMPONENT or {"role", "served_name", "model", "engine", "image"} - set(c):
        raise RecipeError(f"a component has the fields {', '.join(sorted(COMPONENT))}")
    m = c["model"]
    if not isinstance(m, dict) or set(m) - {"repo", "revision", "include"}:
        raise RecipeError("model: {repo, revision, include?}")
    if not isinstance(m.get("include", []), list):
        raise RecipeError("model.include is a list of patterns")
    if not REPO_RE.fullmatch(str(m.get("repo"))) or not REV_RE.fullmatch(str(m.get("revision"))):
        raise RecipeError("model: a repo id and a 40-hex commit")
    include = tuple(m.get("include") or ())
    for p in include:
        if not isinstance(p, str) or not PATTERN_RE.fullmatch(p) or ".." in p.split("/") or p.startswith("/"):
            raise RecipeError(f"model.include: bad pattern {p!r}")
    if c["role"] not in ROLES:
        raise RecipeError(f"role: one of {', '.join(sorted(ROLES))}")
    draft = c.get("draft")
    if draft is not None and (not isinstance(draft, dict) or set(draft) != {"repo", "revision"}
                              or not REPO_RE.fullmatch(str(draft["repo"])) or not REV_RE.fullmatch(str(draft["revision"]))):
        raise RecipeError("draft: {repo, revision} with a 40-hex commit")
    args = dict(c.get("args") or {})
    sc = args.get("speculative-config")
    if isinstance(sc, str):
        try:
            sc = args["speculative-config"] = json.loads(sc)
        except ValueError:
            raise RecipeError("speculative-config is not JSON") from None
    if (isinstance(sc, dict) and "model" in sc) or "speculative-draft-model-path" in args:
        raise RecipeError("the draft model's path is filled in from draft; a recipe does not name paths")
    # an engine built on the device is named REPO@local: its image ID is this machine's own
    image = c["image"]
    if isinstance(image, str) and image.endswith("@local"):
        engine = spec_mod.ENGINES.get(c["engine"]) or {}
        repo = image[:-len("@local")]
        if not spec_mod.is_local(repo) or not spec_mod._image_allowed(repo, engine.get("images", ())):
            raise RecipeError(f"{image}: only an engine built on the device is named @local")
        image = image[:-len("@local")] + "@sha256:" + "0" * 64
    # the engine, image, name, arguments and environment get the same checks as an instance spec
    probe = {"id": "recipe-check", "engine": c["engine"], "image": image, "role": c["role"],
             "model": f"models--x--y/snapshots/{'0' * 40}", "served_name": c["served_name"],
             "port": spec_mod.INSTANCE_PORTS.start, "args": args, "env": c.get("env", {}), "memory_gib": c.get("memory_gib")}
    try:
        spec_mod.load(probe)
    except spec_mod.SpecError as e:
        raise RecipeError(f"component {c.get('served_name')!r}: {e}") from None
    return Component(c["role"], c["served_name"], m["repo"], m["revision"], include, c["engine"], c["image"],
                     args, dict(c.get("env", {})),
                     draft["repo"] if draft else None, draft["revision"] if draft else None, c.get("memory_gib"))


def load(data):
    if not isinstance(data, dict) or set(data) - TOP or TOP - {"description", "source"} - set(data):
        raise RecipeError(f"a recipe has the fields {', '.join(sorted(TOP))}")
    if data["schema"] != 1:
        raise RecipeError("only schema 1 is understood")
    types = {"title": str, "description": str, "source": str, "platforms": list, "requires": dict,
             "components": list, "agents": dict}
    for k, t in types.items():
        if k in data and not isinstance(data[k], t):
            raise RecipeError(f"{k} must be a {t.__name__}")
    if not all(isinstance(p, str) for p in data["platforms"]):
        raise RecipeError("platforms are strings")
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in data["requires"].values()):
        raise RecipeError("requires holds whole numbers")
    if not ID_RE.fullmatch(str(data["id"])):
        raise RecipeError("id: lowercase letters, digits and dashes")
    comps = tuple(_component(c) for c in data.get("components") or [])
    if not comps:
        raise RecipeError("a recipe has at least one component")
    names = [c.served_name for c in comps]
    if len(set(names)) != len(names):
        raise RecipeError("two components serve the same name")
    ids = [instance_id(n) for n in names]
    if len(set(ids)) != len(ids):
        raise RecipeError("two components would be the same instance (names differing only in punctuation)")
    req = data["requires"]
    default = (data.get("agents") or {}).get("default_model")
    if default not in names:
        raise RecipeError("agents.default_model must be one of the components")
    return Recipe(data["id"], str(data["title"]), str(data.get("description", "")), tuple(data["platforms"]),
                  int(req.get("memory_gib", 0)), int(req.get("disk_gib", 0)), str(data.get("source", "")),
                  comps, default)


# A drop-in's file name is the identity it signs under, so the name is checked as strictly as an
# id: a file called "recipes@raytone.ai" would otherwise verify and be reported as the Lab's own
# key, which is the single thing this whole arrangement exists to prevent (codex review).
LOCAL_SIGNER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
KEY_TYPE_RE = re.compile(r"^(ssh-|ecdsa-|sk-ssh-|sk-ecdsa-)[A-Za-z0-9@.+-]+$")
# O_DIRECTORY and O_NOFOLLOW are POSIX. They are what stops a symlink in the signers directory
# from being followed, so on a platform without them this whole path is unavailable rather than
# quietly weaker -- which is academic, since the app ships for the Linux it is written against.
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
# O_NONBLOCK, because opening a FIFO for reading waits for a writer that may never come: a FIFO
# named like a signer would wedge the whole read before the "not a regular file" check could refuse
# it. It is a no-op on regular files, which is all this directory is ever supposed to hold.
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
# errno values that say this process or machine ran out of descriptors or memory. Those are not
# facts about the key file in hand, so they must not be reported as "this key is broken" once per
# file -- they stop the whole read.
_EXHAUSTED = frozenset(e for e in (getattr(errno, n, None)
                                   for n in ("EMFILE", "ENFILE", "ENOMEM")) if e is not None)
MAX_LOCAL_SIGNERS = 16          # bounds recipes x signers, and ssh-keygen runs, per read
MAX_SIGNERS_BYTES = 64 * 1024
VERIFY_TIMEOUT = 20


def local_signers(d=LOCAL_SIGNERS_DIR, problems=None):
    """(identity, allowed_signers line) for each dropped-in key. The identity is the file's name.

    The line is returned as bytes read from the descriptor we checked, not as a path, because
    anything that re-opens by path afterwards is checking one inode and trusting another.

    A problem with the DIRECTORY disables local trust entirely -- that is root's own configuration, and if it
    cannot be read as root's then none of it can be believed. A problem with a single FILE skips
    that file and is appended to `problems`, so one unreadable key does not take the other keys
    with it, and the caller can report it once about the directory instead of once per recipe.
    """
    if d is None:
        return []
    d = pathlib.Path(d)
    def note(msg):
        if problems is not None:
            problems.append(msg)
    try:
        # O_NOFOLLOW: a symlink in this position raises rather than being followed. Everything
        # below goes through this descriptor, so the directory cannot be swapped underneath us.
        dfd = os.open(d, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW)
    except FileNotFoundError:
        return []                               # not configured on this machine: not an error
    except NotADirectoryError:
        raise RecipeError(f"{d}: is not a directory, so the keys in it are not root's to pin") from None
    except OSError as e:
        raise RecipeError(f"{d}: cannot be read ({e.strerror})") from None
    try:
        _require_root_owned(d, os.fstat(dfd))
        try:
            names = sorted(os.listdir(dfd))
        except OSError as e:
            raise RecipeError(f"{d}: cannot be read ({e.strerror})") from None
        out, considered = [], 0
        for name in names:
            if name.startswith("."):
                continue
            if not LOCAL_SIGNER_RE.fullmatch(name) or name == SIGNER:
                note(f"{name}: a signer file is named like an id, and never {SIGNER!r}")
                continue
            # count what is opened, not what parses: each candidate costs an open and a
            # ssh-keygen run, so counting only the successes bounds nothing
            considered += 1
            if considered > MAX_LOCAL_SIGNERS:
                raise RecipeError(f"{d}: more than {MAX_LOCAL_SIGNERS} local signers")
            line = _read_signer(dfd, name, note)
            if line is None:
                continue
            out.append((name, line))
        return out
    finally:
        os.close(dfd)


def _read_signer(dfd, name, note):
    """The one allowed_signers line in `name`, or None with a note saying why not."""
    try:
        fd = os.open(name, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK, dir_fd=dfd)
    except OSError as e:
        if e.errno in _EXHAUSTED:
            raise RecipeError(f"the signers directory cannot be read ({e.strerror})") from None
        note(f"{name}: cannot be opened ({e.strerror})")
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            note(f"{name}: a signer file is a regular file, not a link or device")
            return None
        try:
            _require_root_owned(pathlib.PurePath(name), st)
        except RecipeError as e:
            note(str(e))
            return None
        if not 0 < st.st_size <= MAX_SIGNERS_BYTES:
            note(f"{name}: a signer file holds one key, and is not empty")
            return None
        raw = os.read(fd, MAX_SIGNERS_BYTES)
    except OSError as e:
        if e.errno in _EXHAUSTED:
            raise RecipeError(f"the signers directory cannot be read ({e.strerror})") from None
        note(f"{name}: cannot be read ({e.strerror})")
        return None
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        note(f"{name}: is not text, so it is not an allowed_signers line")
        return None
    key = _sole_key(name, text)
    if key is None:
        note(f"{name}: holds exactly one key, whose principal is {name!r}")
        return None
    if not _is_a_public_key(*key):
        note(f"{name}: names a key type but not a key ssh-keygen recognises")
        return None
    return raw


def _split_fields(line):
    """Yield (field, inside an unclosed quote) for each whitespace-separated field, keeping a
    double-quoted option value whole.

    OpenSSH's options scanner treats only a backslash before a double quote as an escape, and does
    not require that it already be inside quotes -- so that is the only escape honoured here, and
    honoured in both states. The quotes stay in the token, so a value holding a word like
    ssh-ed25519 can never match KEY_TYPE_RE.
    """
    cur, quoted, i = [], False, 0
    q = '"'
    bs = chr(92)
    while i < len(line):
        c = line[i]
        if c == bs and i + 1 < len(line) and line[i + 1] == q:
            cur.append(c)
            cur.append(q)
            i += 2
            continue
        if c == q:
            quoted = not quoted
            cur.append(c)
            i += 1
            continue
        if not quoted and (c == " " or c == chr(9)):
            if cur:
                yield "".join(cur), quoted
                cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if cur:
        yield "".join(cur), quoted


def _sole_key(name, text):
    """(key type, key) from the single record in a drop-in file, or None.

    An allowed_signers record is `principal [options] keytype key [comment]`. The options sit
    between the principal and the key type -- `namespaces="raytone-recipe"` is the one that matters
    here -- so the key type is found rather than assumed to be the second field.

    Scanning stops as soon as the key is in hand. What follows is a comment, and its quoting is not
    part of this grammar: `nvidia@thor "spare key"` is a legal comment, and a lone quote in one must
    not make the record unreadable.
    """
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if len(lines) != 1:
        return None
    fields = []
    for field, unclosed in _split_fields(lines[0]):
        fields.append(field)
        if fields[0] != name:
            return None
        if len(fields) >= 3 and KEY_TYPE_RE.fullmatch(fields[-2]):
            return fields[-2], fields[-1]
        if unclosed:
            return None     # an option's quote never closed, so every field after it is a guess
    return None


def _is_a_public_key(keytype, key):
    """Whether ssh-keygen reads these two fields as a key. A key type with a plausible name in
    front of something that is not a key would otherwise pass to verification and come back as
    "the signature does not verify", blaming the recipe for a malformed key file."""
    try:
        with tempfile.TemporaryDirectory() as t:
            # TemporaryDirectory is 0700 and unpredictable, so a fixed name inside it is not a
            # path anyone else can pre-empt with a symlink
            f = pathlib.Path(t) / "key.pub"
            f.write_text(keytype + " " + key + chr(10), encoding="utf-8")
            try:
                r = subprocess.run(["ssh-keygen", "-l", "-f", str(f)],
                                   capture_output=True, timeout=VERIFY_TIMEOUT)
            except subprocess.TimeoutExpired:
                return False
    except FileNotFoundError:
        # no ssh-keygen is a fact about the machine, not about this key: every recipe is
        # unverifiable, and saying "this key is malformed" about each one would be a lie
        raise RecipeError("ssh-keygen is not installed, so no signature can be checked") from None
    except OSError as e:
        raise RecipeError(f"ssh-keygen could not be run ({e.strerror})") from None
    return r.returncode == 0


def _require_root_owned(path, st=None):
    """Root's, and only root's, to rewrite. `st` is the caller's own fstat()/lstat() so the check
    reads the inode the caller is actually holding rather than re-resolving the path."""
    if st is None:
        st = path.lstat()
    if st.st_uid != 0:
        raise RecipeError(f"{path.name}: trusting a signing key is root's to decide, and this is not root's")
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RecipeError(f"{path.name}: is group- or world-writable, so the key in it is not pinned")


def _verified_by(data, sig, signers, identity):
    try:
        r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", identity,
                            "-n", NAMESPACE, "-s", str(sig)], input=data, capture_output=True,
                           timeout=VERIFY_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0


def verify(data, sig, allowed_signers=ALLOWED_SIGNERS, name="recipe", local_dir=LOCAL_SIGNERS_DIR,
           signers=None):
    """The signature over these bytes (the signature file may change: it cannot make other bytes
    valid). Returns the identity that vouched for it: SIGNER for the Lab's key, otherwise the name
    of the dropped-in file, so a caller can tell the two apart and say so.

    `signers` is the already-read local trust store; pass it to read the directory once for a whole
    set of recipes instead of once each. Omit it and this reads `local_dir` itself."""
    sig = pathlib.Path(sig)
    if not sig.exists():
        raise RecipeError(f"{name} is not signed")
    if _verified_by(data, sig, allowed_signers, SIGNER):
        return SIGNER
    if signers is None:
        signers = local_signers(local_dir)
    for identity, line in signers:
        # ssh-keygen takes a path, so write out the bytes we read through the checked descriptor
        # into a file only this process can reach, rather than handing it back the original path
        with tempfile.TemporaryDirectory() as t:
            f = pathlib.Path(t) / "allowed_signers"
            f.write_bytes(line)
            if _verified_by(data, sig, f, identity):
                return identity
    raise RecipeError(f"{name}: the signature does not verify")


def read(path, allowed_signers=ALLOWED_SIGNERS, local_dir=LOCAL_SIGNERS_DIR, signers=None):
    """A recipe file, read once: the bytes verified are the bytes parsed."""
    path = pathlib.Path(path)
    data = path.read_bytes()
    signed_by = verify(data, str(path) + ".sig", allowed_signers, name=path.name,
                       local_dir=local_dir, signers=signers)
    try:
        return dataclasses.replace(load(json.loads(data)), signed_by=signed_by)
    except ValueError as e:
        raise RecipeError(f"{path.name}: {e}") from None


def _snapshot(c, hf_home, draft=False):
    repo, rev = (c.draft_repo, c.draft_revision) if draft else (c.repo, c.revision)
    for m in store.list_models(hf_home):
        if m.repo == repo and m.revision == rev:
            return m
    return None


def _complete(m, include=()):
    """Only the revision manifest proves a download is whole. With include patterns, every file of
    the manifest that a pattern matches must be here, and each pattern must match something."""
    if m is None or m.complete is None:
        return False
    if not include:
        return m.complete and not m.incomplete
    known = set(m.files) | set(m.missing)
    wanted = [f for f in known if any(fnmatch.fnmatch(f, p) for p in include)]
    return (all(any(fnmatch.fnmatch(f, p) for f in known) for p in include)
            and not any(f in m.missing for f in wanted))


def _component_state(c, m):
    return "ready" if _complete(m, c.include) else "missing"


def status(recipe, hf_home=None):
    comps = []
    for c in recipe.components:
        m = _snapshot(c, hf_home)
        state = _component_state(c, m)
        d = _snapshot(c, hf_home, draft=True) if c.draft_repo else None
        if c.draft_repo and not _complete(d):
            state = "missing"
        comps.append({"served_name": c.served_name, "role": c.role, "repo": c.repo, "state": state,
                      "snapshot": m.snapshot if m else None, "draft_snapshot": d.snapshot if d else None,
                      "size": (m.size if m else 0) + (d.size if d else 0)})
    state = "ready" if all(x["state"] == "ready" for x in comps) else "missing"
    return {"id": recipe.id, "title": recipe.title, "state": state, "memory_gib": recipe.memory_gib,
            "disk_gib": recipe.disk_gib, "source": recipe.source, "components": comps}


def instance_id(served_name):
    return re.sub(r"[^a-z0-9-]+", "-", served_name.lower()).strip("-")[:64]


def _fill_draft(engine, args, path):
    if engine == "sglang":
        args["speculative-draft-model-path"] = path
    else:
        args["speculative-config"] = {**args.get("speculative-config", {}), "model": path}


def _image(c, images, strict):
    """The image a component runs: its pinned digest, or for an engine built on the device the image
    ID this machine recorded (scripts/build-engine)."""
    if not c.image.endswith("@local"):
        return c.image
    repo = c.image[:-len("@local")]
    for e in (images or {}).values():
        built = (e or {}).get("image") if isinstance(e, dict) else None
        if isinstance(built, str) and built.startswith(repo + "@sha256:"):
            return built
    if strict:
        raise RecipeError(f"{c.image} is not built on this machine yet: raytone-models-build-engine {repo.split('/', 1)[1]}")
    return c.image


def specs(recipe, hf_home=None, *, used_ports=(), images=None):
    st = status(recipe, hf_home)
    if st["state"] != "ready":
        missing = [c["repo"] for c in st["components"] if c["state"] != "ready"]
        raise RecipeError(f"not downloaded yet: {', '.join(missing)}")
    used, out = set(used_ports), []
    for c, s in zip(recipe.components, st["components"]):
        port = next(p for p in spec_mod.INSTANCE_PORTS if p not in used)
        used.add(port)
        args = dict(c.args)
        if c.draft_repo:
            _fill_draft(c.engine, args, f"/hf/hub/{s['draft_snapshot']}")
        out.append(spec_mod.load({"id": instance_id(c.served_name), "engine": c.engine, "image": _image(c, images, True),
                                  "model": s["snapshot"], "served_name": c.served_name, "port": port,
                                  "args": args, "env": c.env, "memory_gib": c.memory_gib,
                                  "role": c.role}))
    return out


def expected(recipe, hf_home=None, *, images=None):
    """What each downloaded component runs as: {served_name: (image, model, args, env, memory_gib)}."""
    st = status(recipe, hf_home)
    out = {}
    for c, s in zip(recipe.components, st["components"]):
        if s["state"] != "ready":
            continue
        args = dict(c.args)
        if c.draft_repo:
            _fill_draft(c.engine, args, f"/hf/hub/{s['draft_snapshot']}")
        out[c.served_name] = (_image(c, images, False), s["snapshot"], args, c.env, c.memory_gib)
    return out


def fetch_commands(recipe):
    cmds = []
    for c in recipe.components:
        cmd = ["hf", "download", c.repo, "--revision", c.revision]
        for p in c.include:
            cmd += ["--include", p]
        cmds.append(cmd)
        if c.draft_repo:
            cmds.append(["hf", "download", c.draft_repo, "--revision", c.draft_revision])
    return cmds


def available(dirs=(SYSTEM_DIR,), allowed_signers=ALLOWED_SIGNERS, local_dir=LOCAL_SIGNERS_DIR):
    """Every signed recipe found, and why the others were left out."""
    good, bad = [], []
    # Read the local trust store once. A broken drop-in file then shows up as one line about the
    # directory, instead of the same line repeated on every recipe that needed a local key -- which
    # reads as several broken recipes rather than one piece of misconfiguration.
    problems = []
    try:
        signers = local_signers(local_dir, problems)
    except (RecipeError, OSError) as e:
        signers, problems = [], problems + [str(e)]
    bad.extend({"file": str(local_dir), "error": p} for p in problems)
    for d in dirs:
        for f in sorted(pathlib.Path(d).glob("*.json")):
            try:
                good.append(read(f, allowed_signers, local_dir, signers=signers))
            except (RecipeError, OSError) as e:
                bad.append({"file": str(f), "error": str(e)})
    return good, bad
