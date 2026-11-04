"""One native window, with a version-local CLI and a lifetime process lock."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

APP_ID = "ai.raytone.Models"


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError("窗口接口执行失败：" + args[0])
    return result.stdout


def window():
    rows = json.loads(run(["hyprctl", "-j", "clients"]))
    matches = [w for w in rows if w.get("class") == APP_ID]
    if len(matches) > 1:
        raise RuntimeError("发现多个模型控制台窗口，请先关闭多余窗口。")
    if not matches:
        return None
    w = matches[0]
    if not re.fullmatch(r"0x[0-9a-fA-F]+", w.get("address", "")) or type(w.get("pid")) is not int:
        raise RuntimeError("模型控制台窗口身份无效。")
    return w


def activate(w):
    current = window()
    if not current or (current["pid"], current["address"]) != (w["pid"], w["address"]):
        raise RuntimeError("模型控制台窗口刚刚关闭，请重新打开。")
    address = w["address"]
    stable = int(w['stableId'], 16)
    expression = 'raytone_workspace_action("Focus", ' + json.dumps(address) + ', ' + str(w['pid']) + ', ' + str(stable) + ')'
    try:
        if run(["hyprctl", "eval", expression]).strip() != 'ok':
            raise RuntimeError('模型控制台窗口激活未完成。')
    except RuntimeError:
        if w.get("workspace", {}).get("name") in ("special:minimized", "special:hidden"):
            monitors = json.loads(run(["hyprctl", "-j", "monitors"]))
            active = next(m for m in monitors if m.get("focused"))["activeWorkspace"]["id"]
            run(["hyprctl", "dispatch", "movetoworkspacesilent", f"{active},address:{address}"])
        run(["hyprctl", "dispatch", "focuswindow", "address:" + address])


def main():
    try:
        cli = Path(sys.argv[0]).resolve().with_name("raytone-models")
        source_app = cli.parent.parent / "app"
        app = source_app if cli.parent.name == 'bin' else Path("/usr/share/raytone-models/app")
        qs = shutil.which("quickshell") or shutil.which("qs")
        if not qs or not cli.is_file() or not (app / "shell.qml").is_file():
            raise RuntimeError("模型控制台缺少配套程序或 Quickshell。")
        if not os.environ.get("WAYLAND_DISPLAY") or not shutil.which("hyprctl"):
            raise RuntimeError("请在已登录的 Hyprland 桌面打开模型控制台。")
        runtime = Path(os.environ["XDG_RUNTIME_DIR"])
        info = runtime.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise RuntimeError("用户运行目录权限不安全。")
        fd = os.open(runtime / "raytone-models-app.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            if os.fstat(fd).st_uid != os.getuid() or not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RuntimeError("模型控制台锁文件身份无效。")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                for _ in range(60):
                    w = window()
                    if w:
                        activate(w)
                        return 0
                    time.sleep(.1)
                raise RuntimeError("模型控制台启动尚未完成或未响应，请查看启动日志后重试。")
            w = window()
            if w:
                activate(w)
                return 0
            env = dict(os.environ, RAYTONE_MODELS_CLI=str(cli))
            with (runtime / "raytone-models-app.log").open("ab") as log:
                child = subprocess.Popen([qs, "--no-duplicate", "-p", str(app)], env=env,
                                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                         pass_fds=(fd,), start_new_session=True)
            for _ in range(60):
                if child.poll() is not None:
                    raise RuntimeError("模型控制台未能启动，请查看用户运行目录的 raytone-models-app.log。")
                w = window()
                if w:
                    activate(w)
                    return 0
                time.sleep(.1)
            raise RuntimeError("模型控制台窗口启动超时，未重复创建进程。")
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as e:
        print("raytone-models-app: " + str(e), file=sys.stderr)
        return 1
