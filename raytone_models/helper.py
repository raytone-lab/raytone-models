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
import grp
import json
import os
import pathlib
import pwd
import stat
import subprocess
import sys
import tempfile

from . import engines, spec as spec_mod

CONFIG = pathlib.Path("/etc/raytone-models/helper.json")   # {"store": "/home/USER/.local/share/raytone/hf"}
RUN_DIR = pathlib.Path("/run/raytone-models")
CACHE = pathlib.Path("/var/cache/raytone-models")
ENGINE_USER = "raytone-engine"                 # created by the package (sysusers.d)
ENGINE_GROUPS = ("video", "render")            # /dev/nvmap and /dev/dri on the Thor
STORE_ROOT = "/var/lib/raytone-models/"


class HelperError(RuntimeError):
    pass


def _systemctl(args):
    subprocess.run(["systemctl", *args], check=True)


def _engine_user():
    pw = pwd.getpwnam(ENGINE_USER)
    groups = tuple(g.gr_gid for g in (grp.getgrnam(n) for n in ENGINE_GROUPS))
    return (pw.pw_uid, pw.pw_gid), groups


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


def start(text, *, store, run_dir=RUN_DIR, cache=CACHE, systemctl=_systemctl, engine_user=_engine_user, chown=os.chown):
    s = _load(text)
    _check_model(s, store)
    for other_id, other in _registered(run_dir).items():
        if other_id == s.id:
            continue
        if other.port == s.port:
            raise HelperError(f"port {s.port} is used by {other_id}")
        if other.served_name == s.served_name:
            raise HelperError(f"{s.served_name} is already served by {other_id}")
    (uid, gid), _ = engine_user()
    pathlib.Path(cache).mkdir(parents=True, exist_ok=True, mode=0o711)
    mine = pathlib.Path(cache) / s.id
    mine.mkdir(exist_ok=True, mode=0o700)
    os.chmod(mine, 0o700)
    chown(mine, uid, gid)
    _write(_registry(run_dir) / f"{s.id}.json", s.to_json())
    systemctl(["start", f"raytone-engine@{s.id}.service"])
    return s


def _check_id(instance_id):
    if not spec_mod.ID_RE.match(instance_id or ""):
        raise HelperError("bad instance id")


def stop(instance_id, *, store=None, run_dir=RUN_DIR, cache=CACHE, systemctl=_systemctl, **_):
    _check_id(instance_id)
    systemctl(["stop", f"raytone-engine@{instance_id}.service"])
    (_registry(run_dir) / f"{instance_id}.json").unlink(missing_ok=True)


def run_argv(instance_id, *, store, run_dir=RUN_DIR, cache=CACHE, systemctl=None, engine_user=_engine_user, **_):
    _check_id(instance_id)
    try:
        text = (_registry(run_dir) / f"{instance_id}.json").read_text()
    except OSError:
        raise HelperError(f"{instance_id} is not registered") from None
    s = _load(text)
    if s.id != instance_id:
        raise HelperError("registry entry does not match its name")
    _check_model(s, store)
    user, groups = engine_user()
    return engines.docker_argv(s, store=str(store), cache=str(pathlib.Path(cache) / s.id), user=user, groups=groups)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="raytone-models-helper")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("start")
    for name in ("stop", "run"):
        sub.add_parser(name).add_argument("id")
    return p.parse_args(argv)


def check_store(path, *, lstat=os.lstat):
    """The store is checked here and then handed to docker by path, so nobody but root may be able
    to replace it in between: /var/lib/raytone-models/NAME, and every directory from / down to it
    root-owned, not group- or other-writable, and not a link. (What is inside, hub/ and xet/, may
    be the user's: renaming them needs write access to the store itself.)"""
    p = str(path)
    parts = p.split("/")
    if not p.startswith(STORE_ROOT) or len(parts) < 5 or not all(parts[1:]) or ".." in parts or "." in parts:
        raise HelperError(f"store {p!r} must be {STORE_ROOT}NAME")
    for i in range(1, len(parts) + 1):
        prefix = "/".join(parts[:i]) or "/"
        try:
            st = lstat(prefix)
        except OSError:
            raise HelperError(f"store: {prefix} does not exist") from None
        if not stat.S_ISDIR(st.st_mode):
            raise HelperError(f"store: {prefix} is not a directory (or is a link)")
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise HelperError(f"store: {prefix} must be root's and writable by root only")
    return pathlib.Path(p)


def _store_from_config():
    try:
        store = json.loads(CONFIG.read_text())["store"]
    except (OSError, ValueError, KeyError):
        raise HelperError(f"no store configured in {CONFIG}") from None
    return check_store(store)


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
