"""Read the native lock boundary before a new user action; never unlock it."""
import json
import shutil
import subprocess


def require_unlocked(run=subprocess.run):
    try:
        if shutil.which('omarchy-shell'):
            r=run(['omarchy-shell','lock','status'],capture_output=True,text=True,timeout=5)
            value=json.loads(r.stdout)
            if r.returncode or type(value.get('locked')) is not bool:raise ValueError()
            locked=any(value.get(k) for k in ('locked','requested','pending','secure','sessionLocked'))
        else:
            r=run(['loginctl','show-session','auto','-p','Active','-p','LockedHint'],capture_output=True,text=True,timeout=5)
            value=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
            if r.returncode or value.get('Active')!='yes' or value.get('LockedHint') not in ('yes','no'):raise ValueError()
            locked=value['LockedHint']=='yes'
        if locked:raise SystemExit('SESSION_LOCKED：请先用系统密码解锁；本次新操作未执行。')
    except (OSError,ValueError,TypeError,AttributeError,subprocess.SubprocessError):
        raise SystemExit('SESSION_UNAVAILABLE：无法确认本机解锁状态，本次新操作未执行。') from None
