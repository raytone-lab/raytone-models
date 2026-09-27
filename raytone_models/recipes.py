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
COMPONENT = {"role", "served_name", "model", "engine", "image", "args", "env"}
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
    if not REPO_RE.match(str(m.get("repo"))) or not REV_RE.match(str(m.get("revision"))):
        raise RecipeError("model: a repo id and a 40-hex commit")
    include = tuple(m.get("include") or ())
    for p in include:
        if not isinstance(p, str) or not PATTERN_RE.match(p) or ".." in p.split("/") or p.startswith("/"):
            raise RecipeError(f"model.include: bad pattern {p!r}")
    if c["role"] not in ROLES:
        raise RecipeError(f"role: one of {', '.join(sorted(ROLES))}")
    # the engine, image, name, arguments and environment get the same checks as an instance spec
    probe = {"id": "recipe-check", "engine": c["engine"], "image": c["image"],
             "model": f"models--x--y/snapshots/{'0' * 40}", "served_name": c["served_name"],
             "port": spec_mod.INSTANCE_PORTS.start, "args": c.get("args", {}), "env": c.get("env", {})}
    try:
        spec_mod.load(probe)
    except spec_mod.SpecError as e:
        raise RecipeError(f"component {c.get('served_name')!r}: {e}") from None
    return Component(c["role"], c["served_name"], m["repo"], m["revision"], include, c["engine"], c["image"],
                     dict(c.get("args", {})), dict(c.get("env", {})))


def load(data):
    if not isinstance(data, dict) or set(data) - TOP or TOP - {"description", "source"} - set(data):
        raise RecipeError(f"a recipe has the fields {', '.join(sorted(TOP))}")
    if data["schema"] != 1:
        raise RecipeError("only schema 1 is understood")
    if not ID_RE.match(str(data["id"])):
        raise RecipeError("id: lowercase letters, digits and dashes")
    comps = tuple(_component(c) for c in data.get("components") or [])
    if not comps:
        raise RecipeError("a recipe has at least one component")
    names = [c.served_name for c in comps]
    if len(set(names)) != len(names):
        raise RecipeError("two components serve the same name")
    req = data["requires"]
    default = (data.get("agents") or {}).get("default_model")
    if default not in names:
        raise RecipeError("agents.default_model must be one of the components")
    return Recipe(data["id"], str(data["title"]), str(data.get("description", "")), tuple(data["platforms"]),
                  int(req.get("memory_gib", 0)), int(req.get("disk_gib", 0)), str(data.get("source", "")),
                  comps, default)


def verify(path, allowed_signers=ALLOWED_SIGNERS):
    path = pathlib.Path(path)
    sig = pathlib.Path(str(path) + ".sig")
    if not sig.exists():
        raise RecipeError(f"{path.name} is not signed")
    with open(path, "rb") as f:
        r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", SIGNER,
                            "-n", NAMESPACE, "-s", str(sig)], stdin=f, capture_output=True)
    if r.returncode:
        raise RecipeError(f"{path.name}: the signature does not verify")


def read(path, allowed_signers=ALLOWED_SIGNERS):
    """A recipe file, verified first and parsed from the very bytes that were verified."""
    path = pathlib.Path(path)
    data = path.read_bytes()
    verify(path, allowed_signers)
    if path.read_bytes() != data:
        raise RecipeError(f"{path.name} changed while it was checked")
    try:
        return load(json.loads(data))
    except ValueError as e:
        raise RecipeError(f"{path.name}: {e}") from None


def _snapshot(c, hf_home):
    for m in store.list_models(hf_home):
        if m.repo == c.repo and m.revision == c.revision:
            return m
    return None


def _component_state(c, m):
    if m is None:
        return "missing"
    if c.include:
        # a partial download: only the recipe's files count, not everything the revision has
        wanted = lambda f: any(fnmatch.fnmatch(f, p) for p in c.include)
        if any(wanted(f) for f in m.missing):
            return "missing"
        if not all(any(fnmatch.fnmatch(f, p) for f in m.files) for p in c.include):
            return "missing"
        return "ready"
    if m.complete is False or m.missing or m.incomplete:
        return "missing"
    return "ready"


def status(recipe, hf_home=None):
    comps = []
    for c in recipe.components:
        m = _snapshot(c, hf_home)
        comps.append({"served_name": c.served_name, "role": c.role, "repo": c.repo, "state": _component_state(c, m),
                      "snapshot": m.snapshot if m else None, "size": m.size if m else 0})
    state = "ready" if all(x["state"] == "ready" for x in comps) else "missing"
    return {"id": recipe.id, "title": recipe.title, "state": state, "memory_gib": recipe.memory_gib,
            "disk_gib": recipe.disk_gib, "source": recipe.source, "components": comps}


def instance_id(served_name):
    return re.sub(r"[^a-z0-9-]+", "-", served_name.lower()).strip("-")[:64]


def specs(recipe, hf_home=None, *, used_ports=()):
    st = status(recipe, hf_home)
    if st["state"] != "ready":
        missing = [c["repo"] for c in st["components"] if c["state"] != "ready"]
        raise RecipeError(f"not downloaded yet: {', '.join(missing)}")
    used, out = set(used_ports), []
    for c, s in zip(recipe.components, st["components"]):
        port = next(p for p in spec_mod.INSTANCE_PORTS if p not in used)
        used.add(port)
        out.append(spec_mod.load({"id": instance_id(c.served_name), "engine": c.engine, "image": c.image,
                                  "model": s["snapshot"], "served_name": c.served_name, "port": port,
                                  "args": c.args, "env": c.env}))
    return out


def fetch_commands(recipe):
    cmds = []
    for c in recipe.components:
        cmd = ["hf", "download", c.repo, "--revision", c.revision]
        for p in c.include:
            cmd += ["--include", p]
        cmds.append(cmd)
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
