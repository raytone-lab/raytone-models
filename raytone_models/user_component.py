"""User code only. Transactional install/rollback/recover, no model or system changes."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import tempfile

from .system_contract import VERSION


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(path):
    if path.is_symlink():
        return {'link': os.readlink(path)}
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError('受管目标不是普通文件：' + str(path))
    return {'data': base64.b64encode(path.read_bytes()).decode(), 'mode': stat.S_IMODE(path.stat().st_mode)}


def replace(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if value is None:
        path.unlink(missing_ok=True)
        return
    tmp = path.with_name(path.name + '.models-new')
    tmp.unlink(missing_ok=True)
    if 'link' in value:
        tmp.symlink_to(value['link'])
    else:
        tmp.write_bytes(base64.b64decode(value['data'])); tmp.chmod(value['mode'])
    os.replace(tmp, path)


def file_value(text, mode=0o644):
    return {'data': base64.b64encode(text.encode()).decode(), 'mode': mode}


class Component:
    def __init__(self):
        self.home = Path.home()
        self.data = Path(os.environ.get('XDG_DATA_HOME', self.home / '.local/share'))
        if not self.data.is_absolute():
            raise ValueError('XDG_DATA_HOME 必须是绝对路径。')
        self.root = self.data / 'raytone/models-component'
        self.receipt = self.root / 'installed.json'
        self.pending = self.root / 'pending.json'
        self.targets = {'current': self.root / 'current', 'cli': self.home / '.local/bin/raytone-models',
                        'app': self.home / '.local/bin/raytone-models-app',
                        'desktop': self.data / 'applications/ai.raytone.Models.desktop'}

    def safe(self, path):
        for p in path.parents:
            if p == self.home.parent: break
            if p.is_symlink(): raise ValueError('安装目录含符号链接：' + str(p))

    def read(self):
        if not self.receipt.exists(): return None
        if self.receipt.is_symlink(): raise ValueError('组件收据不能为链接。')
        value = json.loads(self.receipt.read_text())
        if value.get('kind') != 'raytone-models-user' or value.get('schema') != 1:
            raise ValueError('组件收据版本无效。')
        return value

    def recover(self):
        if not self.pending.exists(): return {'recovered': False}
        journal = json.loads(self.pending.read_text())
        if set(journal['before']) != set(self.targets) or set(journal['after']) != set(self.targets):
            raise ValueError('组件恢复记录不完整。')
        for key, path in self.targets.items():
            self.safe(path)
            current = encoded(path)
            if current not in (journal['before'][key], journal['after'][key]):
                raise ValueError('组件入口在中断后被修改，保留恢复记录：' + str(path))
        for key, path in self.targets.items(): replace(path, journal['before'][key])
        replace(self.receipt, journal['receipt'])
        self.pending.unlink()
        return {'recovered': True}

    def install(self, source):
        if self.pending.exists(): self.recover()
        source = Path(source).resolve()
        files = {}
        for directory in ('app', 'bin', 'raytone_models', 'recipes'):
            for path in sorted((source / directory).rglob('*')):
                if '__pycache__' in path.parts or path.suffix == '.pyc' or not path.is_file(): continue
                if path.is_symlink(): raise ValueError('组件源不能含文件链接。')
                name = str(path.relative_to(source))
                if name == 'bin/raytone-models-helper': continue
                files[name] = {'sha256': sha(path.read_bytes()), 'mode': stat.S_IMODE(path.stat().st_mode)}
        for name in ('LICENSE', 'packaging/allowed_signers'):
            files[name] = {'sha256': sha((source/name).read_bytes()), 'mode': 0o644}
        required = ('app/shell.qml','bin/raytone-models','bin/raytone-models-app','raytone_models/cli.py')
        if any(name not in files for name in required): raise ValueError('组件缺少程序。')
        identity = sha(json.dumps(files, sort_keys=True).encode())
        release = self.root/'releases'/identity
        if not release.exists():
            release.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix='.stage-',dir=release.parent))
            try:
                for name, meta in files.items():
                    path=staging/name;path.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source/name,path);path.chmod(meta['mode'])
                os.replace(staging,release)
            finally:
                if staging.exists(): shutil.rmtree(staging)
        for name, meta in files.items():
            path=release/name
            if path.is_symlink() or sha(path.read_bytes()) != meta['sha256'] or stat.S_IMODE(path.stat().st_mode) != meta['mode']:
                raise ValueError('组件版本目录已被修改。')
        before = self.read()
        after = {'current': {'link': 'releases/'+identity}}
        for key, name in (('cli','raytone-models'),('app','raytone-models-app')):
            after[key] = file_value('#!/bin/sh\n# Raytone Models managed entry\nexec '+shlex.quote(str(self.root/'current/bin'/name))+' "$@"\n',0o755)
        after['desktop'] = file_value('[Desktop Entry]\nType=Application\nName=模型控制台\nExec="'+str(self.targets['app'])+'"\nIcon='+str(self.root/'current/app/brand/raytone-symbol-color.svg')+'\nTerminal=false\nStartupWMClass=ai.raytone.Models\nCategories=Utility;\n')
        old={}
        for key,path in self.targets.items():
            self.safe(path);old[key]=encoded(path)
            if old[key] != (before or {}).get('managed',{}).get(key):
                raise ValueError('入口不属于组件收据或已修改，未覆盖：'+str(path))
        if before and before['current']==identity and old==after: return {'changed':False,'id':identity}
        journal={'before':old,'after':after,'receipt':encoded(self.receipt)}
        replace(self.pending,file_value(json.dumps(journal)))
        try:
            for key,path in self.targets.items():
                if encoded(path)!=old[key]:raise ValueError('组件入口刚被其他程序修改。')
                replace(path,after[key])
            value={'kind':'raytone-models-user','schema':1,'version':VERSION,'current':identity,
                   'previous':before['current'] if before and before['current']!=identity else (before or {}).get('previous'),
                   'managed':after,'files':files}
            replace(self.receipt,file_value(json.dumps(value)))
            self.pending.unlink()
            return {'changed':True,'id':identity,'version':VERSION}
        except BaseException:
            self.recover();raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('install','rollback','recover','status'))
    parser.add_argument('source',nargs='?',type=Path)
    args=parser.parse_args(argv)
    try:
        component=Component();component.safe(component.root/'lock')
        component.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(component.root/'lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if args.action=='install':
                if args.source is None:raise ValueError('须指定固定组件源目录。')
                result=component.install(args.source)
            elif args.action=='rollback':
                value=component.read() or {};previous=value.get('previous')
                if not isinstance(previous,str) or len(previous)!=64 or any(x not in '0123456789abcdef' for x in previous):raise ValueError('没有可回退的 Models 用户组件。')
                result=component.install(component.root/'releases'/previous)
            elif args.action=='recover':result=component.recover()
            else:result={'installed':component.read(),'needsRecovery':component.pending.exists()}
        print(json.dumps({'ok':True,'data':result},ensure_ascii=False));return 0
    except (OSError,ValueError,KeyError) as error:
        print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
