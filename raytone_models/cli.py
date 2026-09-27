"""raytone-models: the user-facing CLI (and the panel's backend). Every command can answer in JSON.

    raytone-models models [--json]
    raytone-models instances [--json]
    raytone-models start REPO[@REVISION] --engine vllm --name SERVED [--image REPO@sha256:D] [--arg KEY[=VALUE]]... [--json]
    raytone-models stop ID
    raytone-models agents [--json]
    raytone-models agent connect|revert AGENT [--default SERVED] [--json]
    raytone-models hub search QUERY [--kind video|image|speech] [--json]
    raytone-models hub files REPO [--revision COMMIT] [--json]
    raytone-models download REPO[@COMMIT] [--variant NAME | --include PATTERN...] [--json]
    raytone-models downloads [--json]      raytone-models download-cancel ID
    raytone-models delete REPO[@COMMIT]    raytone-models hf-token set|clear   (token on stdin)
    raytone-models stats|engines [--json]  raytone-models chat   (request JSON on stdin, JSON lines out)
    raytone-models video --prompt TEXT [--size 480p|768p] [--seconds N] [--seed N] [--no-turbo]  (JSON lines out)
    raytone-models recipes [--json]
    raytone-models recipe apply|stop|fetch ID [--json]
    raytone-models router [--port 8090]

Starting and stopping go through the privileged helper (pkexec), with the spec on stdin; the CLI
checks the spec first, so the helper sees only what it would accept anyway.
"""
import argparse
import dataclasses
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request

from . import agents, downloads, engines, hf, live, recipes, router, spec as spec_mod, store, video

HELPER = "/usr/lib/raytone-models/raytone-models-helper"
ENGINES_FILE = pathlib.Path(__file__).with_name("engines.json")
LOCAL_ENGINES_FILE = pathlib.Path("/etc/raytone-models/engines.json")
CONFIG_DIR = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")) / "raytone-models"
USER_RECIPES = pathlib.Path(os.environ.get("XDG_DATA_HOME", pathlib.Path.home() / ".local/share")) / "raytone-models/recipes"


def _run(argv, env):
    return subprocess.call(argv, env=env)


def elevate_argv(environ):
    """pkexec from the desktop session (polkit lets the local admin in); sudo for work over SSH."""
    how = environ.get("RAYTONE_MODELS_ELEVATE", "pkexec")
    if how == "pkexec":
        return ["pkexec", HELPER]
    if how == "sudo":
        return ["sudo", "-n", HELPER]
    raise SystemExit("RAYTONE_MODELS_ELEVATE is pkexec or sudo")


def _pkexec(args, stdin=None):
    r = subprocess.run([*elevate_argv(os.environ), *args], input=stdin, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr.strip() or f"helper failed ({r.returncode})")
    return json.loads(r.stdout or "{}")


def _probe(url):
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            return r.status == 200
    except OSError:
        return False


def _engines(files=None):
    """The shipped engine images, with what scripts/build-engine built on this machine over them."""
    out = {}
    for f in files or (ENGINES_FILE, LOCAL_ENGINES_FILE):
        try:
            data = json.loads(pathlib.Path(f).read_text())
        except (OSError, ValueError):
            continue
        for name, e in data.items():
            if isinstance(e, dict):
                out[name] = {**out.get(name, {}), **e}
    return out


@dataclasses.dataclass
class Env:
    hf_home: pathlib.Path = None
    registry: pathlib.Path = router.DEFAULT_REGISTRY
    state: pathlib.Path = agents.STATE
    home: pathlib.Path = None
    engines: dict = None
    helper: object = _pkexec
    probe: object = _probe
    recipe_dirs: list = None
    allowed_signers: pathlib.Path = recipes.ALLOWED_SIGNERS
    run: object = _run
    hf_endpoint: str = None
    spawn: object = downloads._spawn
    downloads_dir: pathlib.Path = downloads.STATE
    config_dir: pathlib.Path = CONFIG_DIR
    counters: object = live.counters
    meminfo: object = live.memory
    videos_dir: pathlib.Path = video.OUT_DIR
    video_poll: float = 1.0

    def __post_init__(self):
        self.hf_home = pathlib.Path(self.hf_home or store.home())
        self.home = pathlib.Path(self.home or pathlib.Path.home())
        if self.engines is None:
            self.engines = _engines()
        if self.recipe_dirs is None:
            self.recipe_dirs = [recipes.SYSTEM_DIR, USER_RECIPES]
        if self.hf_endpoint is None:
            self.hf_endpoint = os.environ.get("HF_ENDPOINT") or hf.DEFAULT_ENDPOINT

    def token(self):
        try:
            return (pathlib.Path(self.config_dir) / "hf-token").read_text().strip() or None
        except OSError:
            return None

    def hub(self):
        return hf.Hub(endpoint=self.hf_endpoint, token=self.token())


def _value(text):
    if text is None:
        return True
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d*", text):
        return float(text)
    if text.startswith("{"):
        return json.loads(text)
    return text


def _registered(env):
    out = []
    for f in sorted(pathlib.Path(env.registry).glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            pass
    return out


def _instances(env):
    out = []
    for d in _registered(env):
        port = d.get("port")
        out.append({"id": d.get("id"), "served_name": d.get("served_name"), "engine": d.get("engine"), "port": port,
                    "context": (d.get("args") or {}).get("max-model-len"),
                    "ready": bool(port) and env.probe(f"http://127.0.0.1:{port}{engines.health_path(d.get('engine'))}")})
    return out


def _find_model(env, ref):
    repo, _, rev = ref.partition("@")
    found = [m for m in store.list_models(env.hf_home) if m.repo == repo and (not rev or m.revision.startswith(rev))]
    if not found:
        raise SystemExit(f"{ref} is not in the store")
    if len(found) > 1:
        raise SystemExit(f"{repo} has several revisions here; name one with @REVISION")
    return found[0]


def _free_port(env):
    used = {d.get("port") for d in _registered(env)}
    return next(p for p in spec_mod.INSTANCE_PORTS if p not in used)


def cmd_start(a, env):
    m = _find_model(env, a.model)
    image = a.image or (env.engines.get(a.engine) or {}).get("image")
    if not image:
        raise SystemExit(f"no image configured for {a.engine}")
    args = {}
    for item in a.arg or []:
        k, eq, v = item.partition("=")
        args[k] = _value(v if eq else None)
    data = {"id": re.sub(r"[^a-z0-9-]+", "-", a.name.lower()).strip("-")[:64], "engine": a.engine, "image": image,
            "model": m.snapshot, "served_name": a.name, "port": a.port or _free_port(env), "args": args, "env": {}}
    try:
        s = spec_mod.load(data)
    except spec_mod.SpecError as e:
        raise SystemExit(f"refused: {e}") from None
    return env.helper(["start"], stdin=s.to_json())


def cmd_agent(a, env):
    ad = agents.get(a.agent, home=env.home, state=env.state)
    if a.action == "revert":
        ad.revert()
        return ad.status()
    ready = [i for i in _instances(env) if i["ready"]]
    if not ready:
        raise SystemExit("no model is running and ready")
    models = [{"id": i["served_name"], "context": i["context"] or 32768, "output": min(32768, (i["context"] or 32768) // 4)}
              for i in ready]
    ad.connect(models, default=a.default or models[0]["id"])
    return ad.status()


def _recipes(env):
    return recipes.available(env.recipe_dirs, env.allowed_signers)


def _recipe(env, rid):
    good, bad = _recipes(env)
    for r in good:
        if r.id == rid:
            return r
    why = next((b["error"] for b in bad if pathlib.Path(b["file"]).stem == rid), "no such recipe")
    raise SystemExit(f"recipe {rid}: {why}")


def _matching(r, env):
    """The recipe's components that run exactly as the recipe says, and those whose name another
    instance serves: {served_name: instance id}, [served_name]."""
    want = recipes.expected(r, env.hf_home, images=env.engines)
    matching, conflicts = {}, []
    for d in _registered(env):
        name = d.get("served_name")
        if name not in {c.served_name for c in r.components}:
            continue
        if name in want and (d.get("image"), d.get("model"), d.get("args") or {}, d.get("env") or {}) == want[name]:
            matching[name] = d.get("id")
        else:
            conflicts.append(name)
    return matching, sorted(set(conflicts))


def cmd_recipes(env):
    good, bad = _recipes(env)
    out = []
    for r in good:
        st = recipes.status(r, env.hf_home)
        matching, conflicts = _matching(r, env)
        st["running"] = len(matching) == len(r.components)
        st["conflicts"] = conflicts
        st["description"] = r.description
        out.append(st)
    return {"recipes": out, "refused": bad}


def cmd_recipe(a, env):
    r = _recipe(env, a.id)
    if a.action == "apply":
        used = {d.get("port") for d in _registered(env)}
        try:
            specs = recipes.specs(r, env.hf_home, used_ports=used, images=env.engines)
        except recipes.RecipeError as e:
            raise SystemExit(str(e)) from None
        # every component checked before any starts: an id another served name uses is not ours to replace
        by_id = {d.get("id"): d.get("served_name") for d in _registered(env)}
        for s in specs:
            other = by_id.get(s.id)
            if other is not None and other != s.served_name:
                raise SystemExit(f"instance {s.id} serves {other}, not {s.served_name}; stop it first")
        return [env.helper(["start"], stdin=s.to_json()) for s in specs]
    if a.action == "stop":
        # only the instances that run as this recipe; another instance with the same name stays
        matching, _ = _matching(r, env)
        return [env.helper(["stop", iid]) for iid in matching.values()]
    hf_env = dict(os.environ, HF_HOME=str(env.hf_home), HF_HUB_DISABLE_TELEMETRY="1")
    for cmd in recipes.fetch_commands(r):
        if env.run(cmd, hf_env):
            raise SystemExit(f"download failed: {' '.join(cmd[:3])}")
    return recipes.status(r, env.hf_home)


def cmd_hub(a, env):
    try:
        if a.action == "search":
            return env.hub().search(a.query, kind=a.kind)
        sha, files = env.hub().files(a.query, a.revision)
        return {"repo": a.query, "revision": sha, "files": files, "variants": hf.variants(files)}
    except hf.HubError as e:
        raise SystemExit(str(e)) from None


def cmd_download(a, env):
    repo, _, rev = a.repo.partition("@")
    try:
        sha, files = env.hub().files(repo, rev or None)
    except hf.HubError as e:
        raise SystemExit(str(e)) from None
    include = list(a.include or [])
    if a.variant:
        v = next((v for v in hf.variants(files) if v["name"] == a.variant), None)
        if v is None:
            raise SystemExit(f"{repo} has no variant {a.variant}")
        include = v["include"]
    try:
        return downloads.start(repo, sha, files, include=include, hf_home=env.hf_home, token=env.token(),
                               state_dir=env.downloads_dir, spawn=env.spawn)
    except downloads.DownloadError as e:
        raise SystemExit(str(e)) from None


def cmd_delete(a, env):
    """The whole repo, or with @COMMIT that revision only (what the app confirms)."""
    repo, _, rev = a.repo.partition("@")
    if rev and not re.fullmatch(r"[0-9a-f]{40}", rev):
        raise SystemExit("a revision to delete is a full 40-hex commit")
    root = "models--" + repo.replace("/", "--")
    if rev and not (pathlib.Path(env.hf_home) / "hub" / root / "snapshots" / rev).is_dir():
        # hf cache rm SHA looks the commit up across the whole cache: it must be this repo's
        raise SystemExit(f"{repo} has no revision {rev} in the store")
    users = [d.get("served_name") for d in _registered(env)
             if (str(d.get("model", "")).endswith(f"/snapshots/{rev}") if rev
                 else str(d.get("model", "")).startswith(root + "/"))]
    if users:
        raise SystemExit(f"{a.repo} is in use by {', '.join(users)}; stop it first")
    hf_env = dict(os.environ, HF_HOME=str(env.hf_home))
    if env.run(["hf", "cache", "rm", rev or f"model/{repo}", "-y"], hf_env):
        raise SystemExit(f"could not delete {a.repo}")
    return {"deleted": a.repo}


def cmd_token(a, env):
    path = pathlib.Path(env.config_dir) / "hf-token"
    if a.action == "clear":
        path.unlink(missing_ok=True)
        return {"token": False}
    token = sys.stdin.readline().strip()
    if not token:
        raise SystemExit("no token on stdin")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token + "\n")
    os.chmod(path, 0o600)
    return {"token": True}


def cmd_video(a, env):
    """JSON lines, like chat: {"state"}..., then {"done": PATH, "seconds"} or {"error"}."""
    def emit(obj):
        print(json.dumps(obj), flush=True)
    found = [d for d in _registered(env) if d.get("engine") == "comfyui" and isinstance(d.get("port"), int)
             and (a.model is None or d.get("served_name") == a.model)]
    if len(found) != 1:
        emit({"error": "no video model is running; start one on Recipes" if not found
              else "several video models are running; name one with --model"})
        return 1
    try:
        wf = video.workflow(a.prompt, size=a.size, seconds=a.seconds, seed=a.seed, turbo=not a.no_turbo)
        video.generate(f"http://127.0.0.1:{found[0]['port']}", wf, env.videos_dir, poll=env.video_poll, emit=emit)
    except video.VideoError as e:
        emit({"error": str(e)})
        return 1
    return 0


def cmd_stats(env):
    import time
    out = []
    for d in _registered(env):
        if isinstance(d.get("port"), int):
            out.append({"id": d.get("id"), "served_name": d.get("served_name"),
                        "counters": env.counters(f"http://127.0.0.1:{d['port']}/metrics")})
    return {"time": time.time(), "memory": env.meminfo(), "instances": out}


def cmd_engines(env):
    names = sorted(set(spec_mod.ENGINES) | {"sglang", "llamacpp", "ollama", "comfyui"})
    rows = []
    for name in names:
        e = env.engines.get(name) or {}
        rows.append({"engine": name, "image": e.get("image"), "tag": e.get("tag"), "checked": e.get("checked"),
                     "configured": bool(e.get("image")) and name in spec_mod.ENGINES})
    return rows


def parse(argv):
    p = argparse.ArgumentParser(prog="raytone-models")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("models", "instances", "agents"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    s = sub.add_parser("start")
    s.add_argument("model")
    s.add_argument("--engine", required=True, choices=sorted(spec_mod.ENGINES))
    s.add_argument("--name", required=True)
    s.add_argument("--port", type=int)
    s.add_argument("--image", help="another image of the engine, pinned by digest (default: the configured one)")
    s.add_argument("--arg", action="append")
    s.add_argument("--json", action="store_true")
    st = sub.add_parser("stop")
    st.add_argument("id")
    st.add_argument("--json", action="store_true")
    ag = sub.add_parser("agent")
    ag.add_argument("action", choices=["connect", "revert"])
    ag.add_argument("agent")
    ag.add_argument("--default")
    ag.add_argument("--json", action="store_true")
    hb = sub.add_parser("hub")
    hb.add_argument("action", choices=["search", "files"])
    hb.add_argument("query")
    hb.add_argument("--kind", choices=sorted(hf.KINDS))
    hb.add_argument("--revision")
    hb.add_argument("--json", action="store_true")
    dl = sub.add_parser("download")
    dl.add_argument("repo")
    dl.add_argument("--variant")
    dl.add_argument("--include", action="append")
    dl.add_argument("--json", action="store_true")
    sub.add_parser("downloads").add_argument("--json", action="store_true")
    dc = sub.add_parser("download-cancel")
    dc.add_argument("id")
    dc.add_argument("--json", action="store_true")
    de = sub.add_parser("delete")
    de.add_argument("repo")
    de.add_argument("--json", action="store_true")
    tk = sub.add_parser("hf-token")
    tk.add_argument("action", choices=["set", "clear"])
    tk.add_argument("--json", action="store_true")
    for name in ("stats", "engines"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    sub.add_parser("chat")
    v = sub.add_parser("video")
    v.add_argument("--prompt", required=True)
    v.add_argument("--model", help="the served name of a ComfyUI instance (the only one when omitted)")
    v.add_argument("--size", default="480p", choices=sorted(video.SIZES))
    v.add_argument("--seconds", type=float, default=5)
    v.add_argument("--seed", type=int, default=0)
    v.add_argument("--no-turbo", action="store_true")
    sub.add_parser("recipes").add_argument("--json", action="store_true")
    rc = sub.add_parser("recipe")
    rc.add_argument("action", choices=["apply", "stop", "fetch"])
    rc.add_argument("id")
    rc.add_argument("--json", action="store_true")
    r = sub.add_parser("router")
    r.add_argument("--port", type=int, default=router.DEFAULT_PORT)
    return p.parse_args(argv)


def _print(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=None, default=str))
    elif isinstance(obj, list):
        for row in obj:
            print("  ".join(f"{v}" for v in row.values()))
    else:
        print(obj)


def _models(env):
    """Local models; each carries the download that brought it in, if any. A variant download is
    complete for what was asked even while the revision's full manifest is not."""
    rank = {"running": 0, "done": 1}
    rows = downloads.listing(hf_home=env.hf_home, state_dir=env.downloads_dir)
    out = []
    for m in store.list_models(env.hf_home):
        d = m.to_dict()
        mine = [r for r in rows if r["repo"] == m.repo and r["revision"] == m.revision]
        mine.sort(key=lambda r: rank.get(r["state"], 2))
        if mine:
            d["download"] = mine[0]
        out.append(d)
    return out


def main(argv=None, env=None):
    a = parse(sys.argv[1:] if argv is None else argv)
    env = env or Env()
    try:
        if a.command == "models":
            _print(_models(env), a.json)
        elif a.command == "instances":
            _print(_instances(env), a.json)
        elif a.command == "agents":
            rows = agents.catalog()
            for r in rows:
                if r["connectable"]:
                    r["connected"] = agents.get(r["id"], home=env.home, state=env.state).status()["connected"]
            _print(rows, a.json)
        elif a.command == "start":
            _print(cmd_start(a, env), a.json)
        elif a.command == "stop":
            _print(env.helper(["stop", a.id]), a.json)
        elif a.command == "agent":
            _print(cmd_agent(a, env), a.json)
        elif a.command == "hub":
            _print(cmd_hub(a, env), a.json)
        elif a.command == "download":
            _print(cmd_download(a, env), a.json)
        elif a.command == "downloads":
            _print(downloads.listing(hf_home=env.hf_home, state_dir=env.downloads_dir), a.json)
        elif a.command == "download-cancel":
            try:
                downloads.cancel(a.id, hf_home=env.hf_home, state_dir=env.downloads_dir)
            except downloads.DownloadError as e:
                raise SystemExit(str(e)) from None
            _print({"cancelled": a.id}, a.json)
        elif a.command == "delete":
            _print(cmd_delete(a, env), a.json)
        elif a.command == "hf-token":
            _print(cmd_token(a, env), a.json)
        elif a.command == "stats":
            _print(cmd_stats(env), a.json)
        elif a.command == "engines":
            _print(cmd_engines(env), a.json)
        elif a.command == "chat":
            return live.chat(f"http://127.0.0.1:{router.DEFAULT_PORT}", live.read_request())
        elif a.command == "video":
            return cmd_video(a, env)
        elif a.command == "recipes":
            _print(cmd_recipes(env), a.json)
        elif a.command == "recipe":
            _print(cmd_recipe(a, env), a.json)
        elif a.command == "router":
            srv = router.make_server("127.0.0.1", a.port)
            srv.serve_forever()
    except agents.AgentError as e:
        print(f"raytone-models: {e}", file=sys.stderr)
        return 1
    except SystemExit as e:
        if isinstance(e.code, str):
            print(f"raytone-models: {e.code}", file=sys.stderr)
            return 1
        raise
    return 0
