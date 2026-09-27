"""Downloads: the official `hf download` in the background, pinned to a commit, into the store.

Each download keeps a small state file (repo, commit, files and sizes from the Hub, pid). Progress
is measured in the store: files already linked into the snapshot, plus the partial blobs
huggingface_hub writes as <sha256>.<random>.incomplete. The token, if any, reaches hf through its
environment only; it is never written to the state file or a command line.

Starting and cancelling hold a lock on the state directory, state files are replaced atomically,
and a process is recognised by its pid together with its start time, so a pid the system has
since given to another process is never signalled.
"""
import contextlib
import fcntl
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import signal
import subprocess

STATE = pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state")) / "raytone-models/downloads"


class DownloadError(RuntimeError):
    pass


def download_id(repo, revision, include):
    tail = hashlib.sha256(json.dumps([repo, revision, sorted(include)]).encode()).hexdigest()[:8]
    return re.sub(r"[^a-z0-9]+", "-", repo.lower()).strip("-")[:48] + "-" + tail


def _identity(pid):
    """The process's start time in clock ticks (/proc/PID/stat field 22); None where there is no /proc."""
    try:
        stat = pathlib.Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return stat.rpartition(")")[2].split()[19]


def _alive(d):
    pid = d.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # without a recorded identity the pid alone proves nothing: never taken for our process
    return d.get("ident") is not None and _identity(pid) == d["ident"]


def _matches(path, patterns):
    # as huggingface_hub filters: fnmatchcase, * crosses directories, "dir/" means everything below
    return any(fnmatch.fnmatchcase(path, p + "*" if p.endswith("/") else p) for p in patterns)


@contextlib.contextmanager
def _locked(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_dir / ".lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def _write(path, d):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, path)


def _spawn(argv, env, log):
    with open(log, "ab") as out:
        return subprocess.Popen(argv, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)


def _kill(pid):
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass


def start(repo, revision, files, *, include=(), hf_home, token=None, state_dir=STATE, spawn=_spawn, alive=_alive,
          identity=_identity):
    include = list(include)
    wanted = [f for f in files if not include or _matches(f["path"], include)]
    if include and not wanted:
        raise DownloadError(f"{', '.join(include)} matches no file in {repo}")
    did = download_id(repo, revision, include)
    state_dir = pathlib.Path(state_dir)
    with _locked(state_dir):
        return _start(repo, revision, include, wanted, did, hf_home, token, state_dir, spawn, alive, identity)


def _start(repo, revision, include, wanted, did, hf_home, token, state_dir, spawn, alive, identity):
    path = state_dir / f"{did}.json"
    if path.exists():
        old = json.loads(path.read_text())
        if old.get("state") == "running" and alive(old):
            raise DownloadError(f"{repo} is already downloading")
    argv = ["hf", "download", repo, "--revision", revision]
    for p in include:
        argv += ["--include", p]
    env = dict(os.environ, HF_HOME=str(hf_home), HF_HUB_DISABLE_TELEMETRY="1")
    env.pop("HF_TOKEN", None)
    if token:
        env["HF_TOKEN"] = token
    proc = spawn(argv, env, state_dir / f"{did}.log")
    d = {"id": did, "repo": repo, "revision": revision, "include": include, "files": wanted,
         "expected": sum(f["size"] for f in wanted), "pid": proc.pid, "ident": identity(proc.pid), "state": "running"}
    _write(path, d)
    return d


def _done_bytes(d, hf_home):
    root = pathlib.Path(hf_home) / "hub" / ("models--" + d["repo"].replace("/", "--"))
    snap = root / "snapshots" / d["revision"]
    done, complete = 0, True
    for f in d["files"]:
        p = snap / f["path"]
        if p.exists():
            done += f["size"]
            continue
        complete = False
        if f.get("sha256"):
            # <sha256>.<random>.incomplete; after a restart there may be more than one
            partial = max((b.stat().st_size for b in (root / "blobs").glob(f"{f['sha256']}*.incomplete")), default=0)
            done += min(partial, f["size"])
    return done, complete


def _row(d, hf_home, alive):
    done, complete = _done_bytes(d, hf_home)
    state = d.get("state", "running")
    if complete:
        state = "done"
    elif state == "running" and not alive(d):
        state = "failed"
    expected = d["expected"] or 1
    return {"id": d["id"], "repo": d["repo"], "revision": d["revision"], "include": d["include"], "state": state,
            "done": done, "expected": d["expected"], "progress": 1.0 if complete else done / expected}


def listing(*, hf_home, state_dir=STATE, alive=_alive, **_):
    out = []
    for f in sorted(pathlib.Path(state_dir).glob("*.json")):
        try:
            out.append(_row(json.loads(f.read_text()), hf_home, alive))
        except (OSError, ValueError, KeyError):
            continue
    return out


def cancel(did, *, hf_home, state_dir=STATE, kill=_kill, alive=_alive, **_):
    state_dir = pathlib.Path(state_dir)
    path = state_dir / f"{did}.json"
    if not re.fullmatch(r"[a-z0-9-]+", did) or not path.exists():
        raise DownloadError(f"no download {did}")
    with _locked(state_dir):
        d = json.loads(path.read_text())
        if _done_bytes(d, hf_home)[1]:
            raise DownloadError(f"{d['repo']} has finished downloading")
        # only the process this download started: its pid may name another process by now
        if d.get("state") == "running" and alive(d):
            kill(d["pid"])
        d["state"] = "cancelled"
        _write(path, d)
