"""User code transactions. Schema 2 keeps maintenance usable across payload rollback."""
import argparse
import ast
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import tempfile

SCHEMA = 2


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(path):
    if path.is_symlink():return {'link': os.readlink(path)}
    if not path.exists():return None
    if not path.is_file():raise ValueError('受管目标不是普通文件：' + str(path))
    return {'data': base64.b64encode(path.read_bytes()).decode(), 'mode': stat.S_IMODE(path.stat().st_mode)}


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def replace(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if value is None:
        path.unlink(missing_ok=True);sync_directory(path.parent);return
    fd,name=tempfile.mkstemp(prefix='.models-',dir=path.parent)
    try:
        if 'link' in value:
            os.close(fd);os.unlink(name);os.symlink(value['link'],name)
        else:
            with os.fdopen(fd,'wb') as f:
                os.fchmod(f.fileno(),value['mode']);f.write(base64.b64decode(value['data']));f.flush();os.fsync(f.fileno())
        os.replace(name,path);sync_directory(path.parent)
    finally:Path(name).unlink(missing_ok=True)


def file_value(text, mode=0o644):
    return {'data': base64.b64encode(text.encode()).decode(), 'mode': mode}


def literal(path,name):
    tree=ast.parse(path.read_text())
    values=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    if len(values)!=1:raise ValueError('组件版本声明无效。')
    return values[0]


def release_matches(release,files):
    if not isinstance(files,dict) or not files:return False
    if any(p.is_symlink() for p in release.rglob('*')):return False
    actual={str(p.relative_to(release)) for p in release.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    if actual!=set(files):return False
    for name,meta in files.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:return False
        path=release/name
        if path.is_symlink() or not path.is_file() or sha(path.read_bytes())!=meta['sha256'] or stat.S_IMODE(path.stat().st_mode)!=meta['mode']:return False
    return True


class Component:
    def __init__(self,live=False):
        self.live=live;self.home=Path.home()
        self.data=Path(os.environ.get('XDG_DATA_HOME',self.home/'.local/share'))
        if not self.data.is_absolute():raise ValueError('XDG_DATA_HOME 必须是绝对路径。')
        self.root=self.data/'raytone/models-component';self.receipt=self.root/'installed.json';self.pending=self.root/'pending.json'
        self.targets={'current':self.root/'current','cli':self.home/'.local/bin/raytone-models',
                      'app':self.home/'.local/bin/raytone-models-app',
                      'router':self.home/'.config/systemd/user/raytone-models-router.service',
                      'desktop':self.data/'applications/ai.raytone.Models.desktop',
                      'maintenance':self.home/'.local/bin/raytone-models-component'}

    def safe(self,path):
        for p in path.parents:
            if p==self.home.parent:break
            if p.is_symlink():raise ValueError('安装目录含符号链接：'+str(p))

    def read(self):
        if not self.receipt.exists():return None
        if self.receipt.is_symlink():raise ValueError('组件收据不能为链接。')
        value=json.loads(self.receipt.read_text())
        if value.get('kind')!='raytone-models-user' or value.get('schema') not in (1,SCHEMA):raise ValueError('组件收据版本无效。')
        if not re.fullmatch('[0-9a-f]{64}',str(value.get('current',''))):raise ValueError('组件版本身份无效。')
        if value.get('managed',{}).get('current')!={'link':'releases/'+value['current']}:raise ValueError('组件入口与版本身份不一致。')
        return value

    def idle(self):
        if not self.live:return
        r=subprocess.run(['/usr/bin/hyprctl','clients','-j'],capture_output=True,text=True,timeout=5)
        rows=json.loads(r.stdout)
        if r.returncode or not isinstance(rows,list):raise ValueError('无法确认图形前端状态，未切换组件。')
        if any(w.get('class') in ('ai.raytone.Models', 'chrome-127.0.0.1__raytone-visual-preview_-Default') for w in rows):
            raise ValueError('请先结束前台对话/视频并关闭模型控制台，再更新组件；后台下载不会由安装器停止。')
        from .workbench import Jobs
        if any(j['phase'] in ('running','unknown') for j in Jobs().recent()):raise ValueError('工作台操作尚未结束，未切换组件。')
        r=subprocess.run(['/usr/bin/systemctl','--user','is-active','raytone-models-router.service'],capture_output=True,text=True,timeout=5)
        if r.stdout.strip() not in ('inactive','failed','unknown'):
            raise ValueError('内部路由仍在运行或状态未知；请在无请求时明确停止该服务，再更新组件。')

    def recover(self):
        if not self.pending.exists():return {'recovered':False}
        self.idle();journal=json.loads(self.pending.read_text());keys=set(journal['before'])
        allowed=[set(self.targets),set(self.targets)-{'maintenance'},set(self.targets)-{'maintenance','router'}]
        if keys not in allowed or set(journal['after'])!=keys:raise ValueError('组件恢复记录不完整。')
        for key in keys:
            path=self.targets[key];self.safe(path)
            if encoded(path) not in (journal['before'][key],journal['after'][key]):raise ValueError('组件入口在中断后被修改，保留恢复记录：'+str(path))
        for key in sorted(keys):replace(self.targets[key],journal['before'][key])
        replace(self.receipt,journal['receipt']);replace(self.pending,None)
        return {'recovered':True}

    def install(self,source):
        if self.pending.exists():self.recover()
        source=Path(source).resolve();version=literal(source/'raytone_models/__init__.py','USER_VERSION')
        if not isinstance(version,str) or not re.fullmatch('[0-9A-Za-z._+-]{1,64}',version):raise ValueError('用户组件版本无效。')
        files={}
        for directory in ('app','bin','raytone_models','recipes','systemd'):
            for path in sorted((source/directory).rglob('*')):
                if '__pycache__' in path.parts or path.suffix=='.pyc' or not path.is_file():continue
                if path.is_symlink():raise ValueError('组件源不能含文件链接。')
                name=str(path.relative_to(source))
                if name=='bin/raytone-models-helper':continue
                files[name]={'sha256':sha(path.read_bytes()),'mode':stat.S_IMODE(path.stat().st_mode)}
        for name in ('LICENSE','packaging/allowed_signers'):files[name]={'sha256':sha((source/name).read_bytes()),'mode':0o644}
        required=('app/shell.qml','bin/raytone-models','bin/raytone-models-app','raytone_models/cli.py')
        if any(n not in files for n in required):raise ValueError('组件缺少程序。')
        identity=sha(json.dumps(files,sort_keys=True).encode());release=self.root/'releases'/identity
        before=self.read()
        new_maintenance='bin/raytone-models-component' in files and literal(source/'raytone_models/user_component.py','SCHEMA')==SCHEMA
        if new_maintenance:maintenance,maintenance_files=identity,files
        else:
            maintenance=(before or {}).get('maintenance');maintenance_files=(before or {}).get('maintenanceFiles')
            if not isinstance(maintenance,str) or not re.fullmatch('[0-9a-f]{64}',maintenance):raise ValueError('请先安装新版组件，再用保留的维护入口回退旧版本。')
            if not release_matches(self.root/'releases'/maintenance,maintenance_files):raise ValueError('保留的维护程序校验失败。')
        if not release.exists():
            release.parent.mkdir(parents=True,exist_ok=True);self.safe(release)
            staging=Path(tempfile.mkdtemp(prefix='.stage-',dir=release.parent))
            try:
                for name,meta in files.items():
                    path=staging/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,path);path.chmod(meta['mode'])
                os.replace(staging,release);sync_directory(release.parent)
            finally:
                if staging.exists():shutil.rmtree(staging)
        if not release_matches(release,files):raise ValueError('组件版本目录已被修改。')
        after={'current':{'link':'releases/'+identity}}
        for key,name in (('cli','raytone-models'),('app','raytone-models-app')):
            after[key]=file_value('#!/bin/sh\n# Raytone Models managed entry\nexec '+shlex.quote(str(self.root/'current/bin'/name))+' "$@"\n',0o755)
        after['maintenance']=file_value('#!/bin/sh\n# Raytone Models pinned maintenance entry\nexec '+shlex.quote(str(self.root/'releases'/maintenance/'bin/raytone-models-component'))+' "$@"\n',0o755)
        launcher = '"' + str(self.targets['app']) + '"'
        desktop = ('[Desktop Entry]\nType=Application\nName=模型控制台\nExec=' + launcher +
                   '\nIcon=' + str(self.root/'current/app/models.svg') +
                   '\nTerminal=false\nStartupWMClass=ai.raytone.Models\nCategories=Utility;\n')
        # Older payloads lack page navigation. Keep rollback's desktop entry compatible with the payload.
        try:
            pages = literal(release/'raytone_models/launcher.py', 'PAGES')
        except (OSError, ValueError):
            pages = ()
        actions = [(page, label) for page, label in (('models', '本地模型'), ('running', '运行中'),
                   ('chat', '对话')) if page in pages]
        if actions:
            desktop += 'Actions=' + ''.join(page + ';' for page, _ in actions) + '\n'
            for page, label in actions:
                desktop += f'\n[Desktop Action {page}]\nName={label}\nExec={launcher} --page {page}\n'
        after['desktop'] = file_value(desktop)
        executable=json.dumps(str(release/'bin/raytone-models'),ensure_ascii=False).replace('%','%%')
        after['router']=file_value('[Unit]\nDescription=Raytone Models internal loopback router\nStartLimitIntervalSec=30\nStartLimitBurst=2\n\n[Service]\nExecStart='+executable+' router\nRestart=on-failure\nRestartSec=2\nNoNewPrivileges=yes\n\n[Install]\nWantedBy=default.target\n')
        old={}
        for key,path in self.targets.items():
            self.safe(path);old[key]=encoded(path)
            if old[key]!=(before or {}).get('managed',{}).get(key):raise ValueError('入口不属于组件收据或已修改，未覆盖：'+str(path))
        if before and before['current']==identity and old==after and before['schema']==SCHEMA:return {'changed':False,'id':identity}
        self.idle();journal={'before':old,'after':after,'receipt':encoded(self.receipt)}
        replace(self.pending,file_value(json.dumps(journal)))
        try:
            for key,path in self.targets.items():
                if encoded(path)!=old[key]:raise ValueError('组件入口刚被其他程序修改。')
                replace(path,after[key])
            value={'kind':'raytone-models-user','schema':SCHEMA,'version':version,'current':identity,
                   'previous':before['current'] if before and before['current']!=identity else (before or {}).get('previous'),
                   'managed':after,'files':files,'maintenance':maintenance,'maintenanceFiles':maintenance_files}
            replace(self.receipt,file_value(json.dumps(value)));replace(self.pending,None)
            return {'changed':True,'id':identity,'version':version,'routerReloadRequired':True}
        except BaseException:
            self.recover();raise

    def status(self):
        value=self.read()
        return {'installed':value,'needsRecovery':self.pending.exists(),
                'filesMatch':bool(value) and all(encoded(self.targets[k])==v for k,v in value['managed'].items()),
                'releaseVerified':bool(value) and release_matches(self.root/'releases'/value['current'],value['files']),
                'maintenanceVerified':bool(value) and value['schema']==SCHEMA and release_matches(self.root/'releases'/value['maintenance'],value['maintenanceFiles'])}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('install','rollback','recover','status'));parser.add_argument('source',nargs='?',type=Path)
    parser.add_argument('--files-only',action='store_true',help='stage an offline image/profile; no live desktop verification')
    args=parser.parse_args(argv)
    try:
        if args.action!='status' and not args.files_only:
            from .session_guard import require_unlocked
            try:require_unlocked()
            except SystemExit as error:raise ValueError(str(error)) from None
        component=Component(live=not args.files_only);component.safe(component.root/'lock');component.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(component.root/'lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if args.action=='install':
                if args.source is None:raise ValueError('须指定固定组件源目录。')
                result=component.install(args.source)
            elif args.action=='rollback':
                value=component.read() or {};previous=value.get('previous')
                if not isinstance(previous,str) or not re.fullmatch('[0-9a-f]{64}',previous):raise ValueError('没有可回退的 Models 用户组件。')
                result=component.install(component.root/'releases'/previous)
            elif args.action=='recover':result=component.recover()
            else:result=component.status()
        print(json.dumps({'ok':True,'data':result},ensure_ascii=False));return 0
    except (OSError,ValueError,KeyError,TypeError,SyntaxError,subprocess.SubprocessError) as error:
        print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
