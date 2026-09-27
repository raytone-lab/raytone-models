"""The privileged helper, the only part of Raytone Models that runs as root.

    raytone-models-helper start      (spec JSON on stdin)  register the instance, start its unit
    raytone-models-helper stop ID                           stop the unit, unregister
    raytone-models-helper run ID                            the unit's ExecStart: exec the docker run

Users reach it through pkexec (polkit action org.raytone.models.manage), which clears the
environment; the paths below are fixed here, never taken from arguments or the environment.
What it runs is only what spec.load() accepts, re-checked at every step, with the model resolved
inside the store: a user who can start engines cannot turn that into root on the host.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

from . import engines, spec as spec_mod

CONFIG = pathlib.Path("/etc/raytone-models/helper.json")   # {"store": "/home/USER/.local/share/raytone/hf"}
RUN_DIR = pathlib.Path("/run/raytone-models")
CACHE = pathlib.Path("/var/cache/raytone-models")


class HelperError(RuntimeError):
    pass


def _systemctl(args):
    subprocess.run(["systemctl", *args], check=True)


def _registry(run_dir):
    return pathlib.Path(run_dir) / "instances"


def _load(text):
    try:
        return spec_mod.load(json.loads(text))
    except (ValueError, spec_mod.SpecError) as e:
        raise HelperError(f"spec refused: {e}") from None


def _check_model(s, store):
    hub = pathlib.Path(store, "hub").resolve()
    snap = (hub / s.model).resolve()
    if not snap.is_dir() or hub not in snap.parents:
        raise HelperError(f"{s.model} is not a snapshot in the store")


def _registered(run_dir):
    out = {}
    for f in _registry(run_dir).glob("*.json"):
        try:
            out[f.stem] = spec_mod.load(json.loads(f.read_text()))
        except (OSError, ValueError, spec_mod.SpecError):
            continue
    return out


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def start(text, *, store, run_dir=RUN_DIR, cache=CACHE, systemctl=_systemctl):
    s = _load(text)
    _check_model(s, store)
    for other_id, other in _registered(run_dir).items():
        if other_id == s.id:
            continue
        if other.port == s.port:
            raise HelperError(f"port {s.port} is used by {other_id}")
        if other.served_name == s.served_name:
            raise HelperError(f"{s.served_name} is already served by {other_id}")
    (pathlib.Path(cache) / s.id).mkdir(parents=True, exist_ok=True)
    _write(_registry(run_dir) / f"{s.id}.json", s.to_json())
    systemctl(["start", f"raytone-engine@{s.id}.service"])
    return s


def _check_id(instance_id):
    if not spec_mod.ID_RE.match(instance_id or ""):
        raise HelperError("bad instance id")


def stop(instance_id, *, store=None, run_dir=RUN_DIR, cache=CACHE, systemctl=_systemctl):
    _check_id(instance_id)
    systemctl(["stop", f"raytone-engine@{instance_id}.service"])
    (_registry(run_dir) / f"{instance_id}.json").unlink(missing_ok=True)


def run_argv(instance_id, *, store, run_dir=RUN_DIR, cache=CACHE, systemctl=None):
    _check_id(instance_id)
    try:
        text = (_registry(run_dir) / f"{instance_id}.json").read_text()
    except OSError:
        raise HelperError(f"{instance_id} is not registered") from None
    s = _load(text)
    if s.id != instance_id:
        raise HelperError("registry entry does not match its name")
    _check_model(s, store)
    return engines.docker_argv(s, store=str(store), cache=str(pathlib.Path(cache) / s.id))


def parse_args(argv):
    p = argparse.ArgumentParser(prog="raytone-models-helper")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("start")
    for name in ("stop", "run"):
        sub.add_parser(name).add_argument("id")
    return p.parse_args(argv)


def _store_from_config():
    try:
        store = json.loads(CONFIG.read_text())["store"]
    except (OSError, ValueError, KeyError):
        raise HelperError(f"no store configured in {CONFIG}") from None
    return pathlib.Path(store)


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        store = _store_from_config()
        if a.command == "start":
            s = start(sys.stdin.read(), store=store)
            print(json.dumps({"started": s.id, "served_name": s.served_name, "port": s.port}))
        elif a.command == "stop":
            stop(a.id, store=store)
            print(json.dumps({"stopped": a.id}))
        else:
            argv = run_argv(a.id, store=store)
            os.execvp(argv[0], argv)
    except (HelperError, subprocess.CalledProcessError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    return 0
