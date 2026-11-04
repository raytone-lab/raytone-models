"""The privileged helper, the only part of Raytone Models that runs as root.

    raytone-models-helper start      (spec JSON on stdin)  register the instance, start its unit
    raytone-models-helper stop ID                           stop the unit, unregister
    raytone-models-helper run ID                            the unit's ExecStart: exec the docker run
    raytone-models-helper unregister ID                     the unit's ExecStopPost

Users reach it through pkexec (polkit action org.raytone.models.manage), which clears the
environment; the paths below are fixed here, never taken from arguments or the environment.
What it runs is only what spec.load() accepts, re-checked at every step, with the model resolved
inside the store: a user who can start engines cannot turn that into root on the host.
"""
import argparse
import fcntl
import grp
import json
import os
import pathlib
import pwd
import re
import stat
import subprocess
import sys
import tempfile

from . import engines, spec as spec_mod

CONFIG = pathlib.Path("/etc/raytone-models/helper.json")   # {"store": "/home/USER/.local/share/raytone/hf"}
LOCAL_ENGINES = pathlib.Path("/etc/raytone-models/engines.json")   # written by build-engine, as root
RUN_DIR = pathlib.Path("/run/raytone-models")
CACHE = pathlib.Path("/var/cache/raytone-models")
ENGINE_USER = "raytone-engine"                 # created by the package (sysusers.d)
ENGINE_GROUPS = ("video", "render")            # /dev/nvmap and /dev/dri on the Thor
STORE_ROOT = "/var/lib/raytone-models/"


class HelperError(RuntimeError):
    pass


def _systemctl(args):
    subprocess.run(["/usr/bin/systemctl", *args], check=True, timeout=75)


def check_subject(environ=None, run=subprocess.run):
    """pkexec authenticates; logind independently refuses a locked/inactive caller."""
    environ=os.environ if environ is None else environ
    uid=environ.get('PKEXEC_UID')
    if uid is None:return  # Explicit root administration and systemd lifecycle.
    if not uid.isdecimal() or int(uid)==0:raise HelperError('AUTH_DENIED：无效的授权主体。')
    try:
        r=run(['/usr/bin/loginctl','show-user',uid,'-p','Display','--value'],capture_output=True,text=True,timeout=5)
        session=r.stdout.strip()
        if r.returncode or not re.fullmatch(r'[A-Za-z0-9]+',session):raise ValueError()
        r=run(['/usr/bin/loginctl','show-session',session,'-p','User','-p','Active','-p','Remote','-p','LockedHint'],capture_output=True,text=True,timeout=5)
        value=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
        if r.returncode or value!={'User':uid,'Active':'yes','Remote':'no','LockedHint':'no'}:raise ValueError()
    except (OSError,ValueError,subprocess.SubprocessError):
        raise HelperError('SESSION_LOCKED：须由已解锁的本机活动会话发起；未执行引擎操作。') from None


def runtime_preflight(s, run=subprocess.run):
    """Check without pulling, stopping, registering or replacing an existing engine."""
    try:
        r=run(['/usr/bin/docker','info','--format','{{.ServerVersion}}'],capture_output=True,text=True,timeout=10)
        if r.returncode or not r.stdout.strip():raise HelperError('DOCKER_UNAVAILABLE：容器服务未就绪。')
        image=s.image.split('@',1)[1] if spec_mod.is_local(s.image) else s.image
        r=run(['/usr/bin/docker','image','inspect','--format','{{.Id}}',image],capture_output=True,text=True,timeout=10)
        if r.returncode:raise HelperError('IMAGE_MISSING：固定镜像不在本机；未自动拉取。')
        if spec_mod.is_local(s.image) and r.stdout.strip()!=image:raise HelperError('IMAGE_MISMATCH：本地镜像身份不匹配。')
        r=run(['/usr/bin/nvidia-ctk','cdi','list'],capture_output=True,text=True,timeout=10)
        if r.returncode or 'nvidia.com/gpu=all' not in r.stdout:raise HelperError('GPU_UNAVAILABLE：NVIDIA CDI推理设备未就绪。')
        r=run(['/usr/bin/systemctl','is-active',f'raytone-engine@{s.id}.service'],capture_output=True,text=True,timeout=5)
        if r.stdout.strip() in ('active','activating','deactivating','reloading'):
            raise HelperError('INSTANCE_BUSY：该引擎仍在运行，未替换。')
    except FileNotFoundError as error:
        raise HelperError('DEPENDENCY_MISSING：缺少系统依赖 '+str(error.filename)) from None
    except (OSError,subprocess.SubprocessError):
        raise HelperError('RUNTIME_UNAVAILABLE：运行环境读取失败，未启动或替换引擎。') from None


def _engine_user():
    pw = pwd.getpwnam(ENGINE_USER)
    groups = tuple(g.gr_gid for g in (grp.getgrnam(n) for n in ENGINE_GROUPS))
    return (pw.pw_uid, pw.pw_gid), groups


def local_images(path=LOCAL_ENGINES, *, lstat=os.lstat):
    """image repository -> the image build-engine recorded, from a root-owned file nobody else can write."""
    try:
        st = lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            return {}
        data = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return {e["image"].split("@", 1)[0]: e["image"] for e in data.values()
            if isinstance(e, dict) and spec_mod.is_local(e.get("image"))}


def _check_image(s, local_images):
    # a local engine runs by its bare image ID: only the ID built and recorded here may run
    if spec_mod.is_local(s.image) and local_images().get(s.image.split("@", 1)[0]) != s.image:
        raise HelperError(f"{s.image} is not the image built on this machine (raytone-models-build-engine)")


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


def start(text, *, store, run_dir=RUN_DIR, cache=CACHE, systemctl=_systemctl, engine_user=_engine_user, chown=os.chown,
          local_images=local_images, preflight=runtime_preflight):
    s = _load(text)
    _check_model(s, store)
    _check_image(s, local_images)
    registered = _registered(run_dir)
    if s.id in registered:
        raise HelperError('INSTANCE_BUSY：实例已登记；请先明确停止，未替换原实例。')
    for other_id, other in registered.items():
        if other_id == s.id:
            continue
        if other.port == s.port:
            raise HelperError(f"port {s.port} is used by {other_id}")
        if other.served_name == s.served_name:
            raise HelperError(f"{s.served_name} is already served by {other_id}")
    preflight(s)
    (uid, gid), _ = engine_user()
    pathlib.Path(cache).mkdir(parents=True, exist_ok=True, mode=0o711)
    mine = pathlib.Path(cache) / s.id
    mine.mkdir(exist_ok=True, mode=0o700)
    os.chmod(mine, 0o700)
    chown(mine, uid, gid)
    unit = f"raytone-engine@{s.id}.service"
    entry = _registry(run_dir) / f"{s.id}.json"
    _write(entry, s.to_json())
    try:
        systemctl(["start", unit])
    except subprocess.CalledProcessError as e:
        entry.unlink(missing_ok=True)
        raise HelperError(f"{unit} did not start ({e.returncode})") from None
    return s


def _check_id(instance_id):
    if not spec_mod.ID_RE.fullmatch(instance_id or ""):
        raise HelperError("bad instance id")


def stop(instance_id, *, store=None, run_dir=RUN_DIR, cache=CACHE, systemctl=_systemctl, **_):
    _check_id(instance_id)
    systemctl(["stop", f"raytone-engine@{instance_id}.service"])
    (_registry(run_dir) / f"{instance_id}.json").unlink(missing_ok=True)


def unregister(instance_id, *, run_dir=RUN_DIR, **_):
    """The unit's ExecStopPost: an engine that ended, however, leaves the registry."""
    _check_id(instance_id)
    (_registry(run_dir) / f"{instance_id}.json").unlink(missing_ok=True)


def run_argv(instance_id, *, store, run_dir=RUN_DIR, cache=CACHE, systemctl=None, engine_user=_engine_user,
             local_images=local_images, **_):
    _check_id(instance_id)
    try:
        text = (_registry(run_dir) / f"{instance_id}.json").read_text()
    except OSError:
        raise HelperError(f"{instance_id} is not registered") from None
    s = _load(text)
    if s.id != instance_id:
        raise HelperError("registry entry does not match its name")
    _check_model(s, store)
    _check_image(s, local_images)
    user, groups = engine_user()
    return engines.docker_argv(s, store=str(store), cache=str(pathlib.Path(cache) / s.id), user=user, groups=groups)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="raytone-models-helper")
    p.add_argument('--protocol', type=int)
    p.add_argument('--component-version')
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("start")
    for name in ("stop", "run", "unregister"):
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
        from . import system_contract
        system_contract.require()
        if (a.protocol, a.component_version) != (system_contract.PROTOCOL, system_contract.VERSION):
            raise HelperError('用户组件版本/协议不匹配。')
        if os.geteuid()!=0:raise HelperError('AUTH_DENIED：此操作须由系统授权执行。')
        check_subject()
        store = _store_from_config()
        if a.command == "start":
            system_contract.trusted(RUN_DIR)
            fd=os.open(RUN_DIR/'manage.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                s = start(sys.stdin.read(131073), store=store)
            print(json.dumps({"started": s.id, "served_name": s.served_name, "port": s.port,'state':'starting','ready':False}))
        elif a.command == "stop":
            system_contract.trusted(RUN_DIR)
            fd=os.open(RUN_DIR/'manage.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                stop(a.id, store=store)
            print(json.dumps({"stopped": a.id}))
        elif a.command == "unregister":
            unregister(a.id)
        else:
            argv = run_argv(a.id, store=store)
            os.execvp(argv[0], argv)
    except (HelperError, OSError, KeyError, subprocess.SubprocessError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    return 0
