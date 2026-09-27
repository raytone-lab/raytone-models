"""raytone-models: the user-facing CLI (and the panel's backend). Every command can answer in JSON.

    raytone-models models [--json]
    raytone-models instances [--json]
    raytone-models start REPO[@REVISION] --engine vllm --name SERVED [--arg KEY[=VALUE]]... [--json]
    raytone-models stop ID
    raytone-models agents [--json]
    raytone-models agent connect|revert AGENT [--default SERVED] [--json]
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

from . import agents, router, spec as spec_mod, store

HELPER = "/usr/lib/raytone-models/raytone-models-helper"
ENGINES_FILE = pathlib.Path(__file__).with_name("engines.json")


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


def _engines():
    try:
        return json.loads(ENGINES_FILE.read_text())
    except (OSError, ValueError):
        return {}


@dataclasses.dataclass
class Env:
    hf_home: pathlib.Path = None
    registry: pathlib.Path = router.DEFAULT_REGISTRY
    state: pathlib.Path = agents.STATE
    home: pathlib.Path = None
    engines: dict = None
    helper: object = _pkexec
    probe: object = _probe

    def __post_init__(self):
        self.hf_home = pathlib.Path(self.hf_home or store.home())
        self.home = pathlib.Path(self.home or pathlib.Path.home())
        if self.engines is None:
            self.engines = _engines()


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
                    "ready": bool(port) and env.probe(f"http://127.0.0.1:{port}/v1/models")})
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
    image = (env.engines.get(a.engine) or {}).get("image")
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


def main(argv=None, env=None):
    a = parse(sys.argv[1:] if argv is None else argv)
    env = env or Env()
    try:
        if a.command == "models":
            _print([m.to_dict() for m in store.list_models(env.hf_home)], a.json)
        elif a.command == "instances":
            _print(_instances(env), a.json)
        elif a.command == "agents":
            _print(agents.catalog(), a.json)
        elif a.command == "start":
            _print(cmd_start(a, env), a.json)
        elif a.command == "stop":
            _print(env.helper(["stop", a.id]), a.json)
        elif a.command == "agent":
            _print(cmd_agent(a, env), a.json)
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
