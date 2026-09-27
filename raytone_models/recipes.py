"""Recipes: Raytone AI Lab's tested combinations of models, engines and parameters.

A recipe is JSON (schema 1) signed with `ssh-keygen -Y sign -n raytone-recipe`; it is used only
when the signature verifies against the allowed signers shipped with the package. Each component
is one instance: a model at a pinned revision (optionally only some of its files), an engine, a
pinned image, and arguments that pass the same checks as any spec.
"""
import dataclasses
import fnmatch
import json
import pathlib
import re
import subprocess

from . import spec as spec_mod, store

NAMESPACE = "raytone-recipe"
SIGNER = "recipes@raytone.ai"
SYSTEM_DIR = pathlib.Path("/usr/share/raytone-models/recipes")
ALLOWED_SIGNERS = pathlib.Path("/usr/share/raytone-models/allowed_signers")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REV_RE = re.compile(r"^[0-9a-f]{40}$")
PATTERN_RE = re.compile(r"^[A-Za-z0-9_.*?/-]{1,200}$")
TOP = {"schema", "id", "title", "description", "platforms", "requires", "source", "components", "agents"}
COMPONENT = {"role", "served_name", "model", "draft", "engine", "image", "args", "env"}
ROLES = {"chat", "coder", "vision", "video", "embedding", "draft"}


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
    if not REPO_RE.match(str(m.get("repo"))) or not REV_RE.match(str(m.get("revision"))):
        raise RecipeError("model: a repo id and a 40-hex commit")
    include = tuple(m.get("include") or ())
    for p in include:
        if not isinstance(p, str) or not PATTERN_RE.match(p) or ".." in p.split("/") or p.startswith("/"):
            raise RecipeError(f"model.include: bad pattern {p!r}")
    if c["role"] not in ROLES:
        raise RecipeError(f"role: one of {', '.join(sorted(ROLES))}")
    draft = c.get("draft")
    if draft is not None and (not isinstance(draft, dict) or set(draft) != {"repo", "revision"}
                              or not REPO_RE.match(str(draft["repo"])) or not REV_RE.match(str(draft["revision"]))):
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
    # the engine, image, name, arguments and environment get the same checks as an instance spec
    probe = {"id": "recipe-check", "engine": c["engine"], "image": c["image"],
             "model": f"models--x--y/snapshots/{'0' * 40}", "served_name": c["served_name"],
             "port": spec_mod.INSTANCE_PORTS.start, "args": args, "env": c.get("env", {})}
    try:
        spec_mod.load(probe)
    except spec_mod.SpecError as e:
        raise RecipeError(f"component {c.get('served_name')!r}: {e}") from None
    return Component(c["role"], c["served_name"], m["repo"], m["revision"], include, c["engine"], c["image"],
                     args, dict(c.get("env", {})),
                     draft["repo"] if draft else None, draft["revision"] if draft else None)


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
    if not ID_RE.match(str(data["id"])):
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


def verify(data, sig, allowed_signers=ALLOWED_SIGNERS, name="recipe"):
    """The signature over these bytes (the signature file may change: it cannot make other bytes valid)."""
    sig = pathlib.Path(sig)
    if not sig.exists():
        raise RecipeError(f"{name} is not signed")
    r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", SIGNER,
                        "-n", NAMESPACE, "-s", str(sig)], input=data, capture_output=True)
    if r.returncode:
        raise RecipeError(f"{name}: the signature does not verify")


def read(path, allowed_signers=ALLOWED_SIGNERS):
    """A recipe file, read once: the bytes verified are the bytes parsed."""
    path = pathlib.Path(path)
    data = path.read_bytes()
    verify(data, str(path) + ".sig", allowed_signers, name=path.name)
    try:
        return load(json.loads(data))
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


def specs(recipe, hf_home=None, *, used_ports=()):
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
        out.append(spec_mod.load({"id": instance_id(c.served_name), "engine": c.engine, "image": c.image,
                                  "model": s["snapshot"], "served_name": c.served_name, "port": port,
                                  "args": args, "env": c.env}))
    return out


def expected(recipe, hf_home=None):
    """What each downloaded component runs as: {served_name: (image, model, args, env)}."""
    st = status(recipe, hf_home)
    out = {}
    for c, s in zip(recipe.components, st["components"]):
        if s["state"] != "ready":
            continue
        args = dict(c.args)
        if c.draft_repo:
            _fill_draft(c.engine, args, f"/hf/hub/{s['draft_snapshot']}")
        out[c.served_name] = (c.image, s["snapshot"], args, c.env)
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


def available(dirs=(SYSTEM_DIR,), allowed_signers=ALLOWED_SIGNERS):
    """Every signed recipe found, and why the others were left out."""
    good, bad = [], []
    for d in dirs:
        for f in sorted(pathlib.Path(d).glob("*.json")):
            try:
                good.append(read(f, allowed_signers))
            except (RecipeError, OSError) as e:
                bad.append({"file": str(f), "error": str(e)})
    return good, bad
