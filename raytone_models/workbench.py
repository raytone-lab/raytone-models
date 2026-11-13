"""Fixed console protocol 1. No HTTP listener, secrets, arbitrary argv or fixture switches.

Durable UUID receipts make browser retries read an existing result. A worker uses
this pinned release, native session/polkit checks and the existing CLI workflows.
Unknown worker outcome is never replayed automatically.
"""
import argparse
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

PROTOCOL = 1
PAGES = ('models', 'recipes', 'agents')
OPERATIONS = {'search': 2, 'detail': 2, 'download': 3, 'download-cancel': 1,
              'model-run': 2, 'instance-stop': 1, 'instance-use': 1,
              'recipe-fetch': 1, 'recipe-apply': 1, 'recipe-stop': 1,
              'agent-connect': 1, 'agent-revert': 1, 'agent-launch': 1, 'agent-web': 1}
READS = {'search', 'detail'}
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}')
REPO = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}')
SHA = re.compile(r'[0-9a-f]{40}')
COMMANDS = {'opencode':'opencode','claude':'claude','codex':'codex','crush':'crush','pi':'pi','omp':'omp','hermes':'hermes','copilot':'copilot','openclaw':'omarchy-launch-openclaw'}
MESSAGES = {'AUTH_CANCELLED':'已取消系统授权。未自动重试；请重新读取状态。',
            'AUTH_DENIED':'系统拒绝授权，请检查本机管理员权限。',
            'SESSION_LOCKED':'请先解锁本机，再重新操作。',
            'SESSION_UNAVAILABLE':'无法确认本机解锁状态，操作未执行。',
            'BUSY':'本机有任务正在处理，请等任务结束后重试。',
            'STATE_UNKNOWN':'无法确认任务状态，操作未执行；请重新读取。',
            'NOT_APPLICABLE':'此配方不适用于当前平台，未启用。',
            'MISSING':'所需组件或资源未备妥，请重新读取详情。',
            'NETWORK':'模型源暂时无法读取，请检查网络后重试。',
            'FAILED':'操作未完成。请重新读取状态后决定是否重试。'}

class Refused(ValueError):
    pass

def txt(v, limit=512):return v[:limit] if isinstance(v,str) else ''
def num(v):return v if type(v) in (int,float) and math.isfinite(v) and v>=0 else None
def rows(v):
    if not isinstance(v,list) or len(v)>2048 or any(not isinstance(x,dict) for x in v):raise ValueError('STATE_UNKNOWN')
    return v

def agent_rows(env):
    from . import agents
    out=[]
    for a in agents.catalog():
        installed=bool(shutil.which(COMMANDS.get(a['id'], 'omarchy-launch-webapp' if a['id']=='codesphere' else a['id'])))
        connected=agents.get(a['id'],home=env.home,state=env.state).status()['connected'] if a['connectable'] else False
        out.append({k:a[k] for k in ('id','name','supported','connectable','web','web_only','reason','note')} | {'connected':connected,'installed':installed})
    return out

def instance_phase(instance):
    if instance.get('ready') is True:return 'ready'
    iid=instance.get('id')
    if not isinstance(iid,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',iid):return 'unknown'
    try:
        r=subprocess.run(['systemctl','show','raytone-engine@'+iid+'.service','--property=LoadState,ActiveState'],capture_output=True,text=True,timeout=3)
        props=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
        if r.returncode or props.get('LoadState')!='loaded':return 'unknown'
        if props.get('ActiveState') in ('failed','inactive'):return 'failed'
        if props.get('ActiveState') in ('active','activating','reloading'):return 'waiting'
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return 'unknown'

def snapshot(page, env):
    from . import cli, downloads, status
    if page not in PAGES:raise ValueError('Invalid page')
    conn=status.snapshot()
    common={'protocol':PROTOCOL,'available':True,'readReady':True,'source':'raytone-models-workbench','reason':'',
            'systemReady':conn['system']['ready'] is True,'downloaderReady':bool(shutil.which('hf'))}
    if page=='agents':return common|{'rows':agent_rows(env)}
    instances=cli._instances(env)
    inst=[{k:x.get(k) for k in ('id','served_name','engine','ready','current','chat','role')} | {'phase':instance_phase(x)} for x in rows(instances)]
    phases={x['id']:x['phase'] for x in inst}
    if page=='recipes':
        data=cli.cmd_recipes(env);out=[]
        for r in rows(data['recipes']):
            matching,conflicts=cli._matching(cli._recipe(env,r['id']),env)
            mine=[x for x in instances if x.get('id') in matching.values()]
            ready=r['running'] and len(mine)==len(matching) and all(x.get('ready') is True for x in mine)
            phase='ready' if ready else 'failed' if any(phases.get(x.get('id'))=='failed' for x in mine) else 'unknown' if any(phases.get(x.get('id'))=='unknown' for x in mine) else 'waiting' if matching else 'conflict' if conflicts else 'prepared' if r['state']=='ready' else r['state']
            out.append({k:r.get(k) for k in ('id','title','description','state','running','memory_gib','applicability')} |
                       {'phase':phase,'conflicts':conflicts,'partial':bool(matching) and not r['running']})
        return common|{'rows':out,'refusedCount':len(data['refused'])}
    out=[]
    registered=cli._registered(env)
    for m in rows(cli._models(env)):
        d=m.get('download') or {};complete=m.get('complete')
        out.append({'id':m['repo'],'revision':m['revision'],'size':num(m.get('size')),
                    'complete':complete if type(complete) is bool else None,'downloadState':txt(d.get('state'),40),
                    'running':any(x.get('model')=='models--'+m['repo'].replace('/','--')+'/snapshots/'+m['revision'] for x in registered),
                    'format':txt(m.get('format'),40),'role':txt(m.get('role'),40),
                    'runnable':(complete is True or d.get('state')=='done') and m.get('role')!='draft' and (m.get('format') in ('gguf','safetensors','pytorch') or (m['repo']=='Comfy-Org/MiniMax-H3' and m['revision']=='bf92c4091e333e69b8ca1998e0a669f15cb0832b'))})
    ds=[{k:d.get(k) for k in ('id','repo','revision','state','done','expected','progress')} for d in downloads.listing(hf_home=env.hf_home,state_dir=env.downloads_dir)]
    return common|{'rows':out,'instances':inst,'downloads':ds[-100:]}

def validate_action(op,args):
    if op not in OPERATIONS or not isinstance(args,list) or len(args)!=OPERATIONS[op]:raise ValueError('Invalid action')
    if any(not isinstance(x,str) or len(x)>512 or any(c in x for c in '\0\r\n') for x in args):raise ValueError('Invalid args')
    if op in ('detail','download','model-run') and not REPO.fullmatch(args[0]):raise ValueError('Invalid repository')
    if op=='detail' and args[1] and not SHA.fullmatch(args[1]):raise ValueError('Invalid revision')
    if op in ('download','model-run') and not SHA.fullmatch(args[1]):raise ValueError('Invalid revision')
    if op=='download' and not args[2]:raise ValueError('Variant required')
    if op=='search' and (not args[0].strip() or len(args[0])>160 or args[1] not in ('','video','image','speech')):raise ValueError('Invalid search')
    if op not in READS|{'download','model-run'} and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,190}',args[0]):raise ValueError('Invalid identity')

def local_json(url):
    with build_opener(ProxyHandler({})).open(url,timeout=3) as response:
        data=response.read(1024*1024+1)
    if len(data)>1024*1024:raise Refused('STATE_UNKNOWN')
    return json.loads(data)

def idle(env):
    """Respect public requests, direct engine work and ComfyUI's native queue. Fail closed."""
    from . import cli, live, connection
    try:
        health=local_json(connection.load().public.removesuffix('/v1')+'/healthz')
        if health.get('event')!='status' or type(health.get('active_requests')) is not int:raise Refused('STATE_UNKNOWN')
        if health['active_requests']:raise Refused('BUSY')
    except URLError as e:
        if not isinstance(e.reason,ConnectionRefusedError):raise Refused('STATE_UNKNOWN') from None
    for x in cli._registered(env):
        port=x.get('port')
        if type(port) is not int or port not in cli.spec_mod.INSTANCE_PORTS:raise Refused('STATE_UNKNOWN')
        if x.get('engine')=='comfyui':
            q=local_json(f'http://127.0.0.1:{port}/queue')
            if not isinstance(q.get('queue_running'),list) or not isinstance(q.get('queue_pending'),list):raise Refused('STATE_UNKNOWN')
            if q['queue_running'] or q['queue_pending']:raise Refused('BUSY')
        else:
            c=live.counters(f'http://127.0.0.1:{port}/metrics')
            if c is None or num(c.get('running')) is None:raise Refused('STATE_UNKNOWN')
            if c['running']:raise Refused('BUSY')

def run_model(args,env):
    from . import cli
    m=next((x for x in cli._models(env) if (x['repo'],x['revision'])==tuple(args)),None)
    if not m or not (m.get('complete') is True or m.get('download',{}).get('state')=='done') or m.get('role')=='draft':raise Refused('MISSING')
    if any(x.get('model','').endswith('/snapshots/'+args[1]) and 'models--'+args[0].replace('/','--')+'/' in x.get('model','') for x in cli._registered(env)):raise Refused('STATE_UNKNOWN')
    ref='@'.join(args);name=re.sub(r'[^a-z0-9.:-]+','-',args[0].split('/')[-1].lower()).strip('-')
    base=['start',ref,'--name',name,'--json']
    if m.get('format')=='gguf':
        files=sorted(f for f in m.get('files',[]) if f.lower().endswith('.gguf'))
        selected=m.get('download',{}).get('include',[])
        from fnmatch import fnmatch
        picked=[f for f in files if any(fnmatch(f,p) for p in selected)]
        models=[f for f in picked or files if 'mmproj' not in f.lower() and not re.search(r'-0000[2-9]-of-|-000[1-9][0-9]-of-',f)]
        if not models:raise Refused('MISSING')
        model=next((f for f in models if 'Q4_K_M' in f),models[0])
        base+=['--engine','llamacpp','--arg','model-file='+model,'--arg','ctx-size=32768','--arg','n-gpu-layers=999','--arg','flash-attn=on','--arg','jinja']
        proj=next((f for f in files if 'mmproj' in f.lower()),None)
        if proj:base+=['--arg','mmproj-file='+proj]
    elif args==['Comfy-Org/MiniMax-H3','bf92c4091e333e69b8ca1998e0a669f15cb0832b'] and all(f in m.get('files',[]) for f in ('diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors','text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors','vae/minimax_h3_video_vae_fp16.safetensors','vae/minimax_h3_audio_vae_fp32.safetensors','loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors')):
        base=['start',ref,'--name','minimax-h3','--engine','comfyui','--role','video','--arg','disable-smart-memory','--json']
    elif m.get('format') in ('safetensors','pytorch') and m.get('role') not in ('video','image'):
        base+=['--engine','vllm','--arg','gpu-memory-utilization=0.6','--arg','max-model-len=65536','--arg','enable-prefix-caching']
        if re.search(r'qwen3\.?8',ref,re.I):base+=['--arg','enable-auto-tool-choice','--arg','tool-call-parser=qwen3_coder','--arg','reasoning-parser=qwen3']
    else:
        # Diffusion engines require signed recipes; never guess a workflow from a repo name.
        raise Refused('MISSING')
    return cli.cmd_start(cli.parse(base),env)

def execute(op,args,env):
    from . import cli, agents, downloads, system_contract
    validate_action(op,args)
    ns=argparse.Namespace
    if op=='search':
        return {'rows':[{k:r.get(k) for k in ('id','downloads','likes','pipeline_tag')} for r in rows(env.hub().search(args[0],kind=args[1] or None))][:100]}
    if op=='detail':
        from . import hf
        rev,files=env.hub().files(args[0],args[1] or None)
        return {'repo':args[0],'revision':rev,'variants':[{k:v.get(k) for k in ('name','size')} for v in hf.variants(files)],'fileCount':len(files)}
    if op in ('download','recipe-fetch') and not shutil.which('hf'):raise Refused('MISSING')
    if op in ('model-run','instance-stop','instance-use','recipe-apply','recipe-stop'):
        system_contract.require();idle(env)
    if op=='model-run':run_model(args,env)
    elif op=='instance-stop':
        if args[0] not in {x['id'] for x in cli._instances(env) if x.get('engine')!='ollama'}:raise Refused('STATE_UNKNOWN')
        env.helper(['stop',args[0]])
    elif op=='instance-use':
        if not any(x.get('served_name')==args[0] and x.get('ready') is True and x.get('chat') is True for x in cli._instances(env)):raise Refused('STATE_UNKNOWN')
        cli.cmd_use(ns(name=args[0]),env)
    elif op=='download':cli.cmd_download(ns(repo=args[0]+'@'+args[1],variant=args[2],include=[]),env)
    elif op=='download-cancel':downloads.cancel(args[0],hf_home=env.hf_home,state_dir=env.downloads_dir)
    elif op.startswith('recipe-'):
        action=op.removeprefix('recipe-')
        r=cli._recipe(env,args[0]) # signature rechecked even when invoked directly
        if action=='apply':
            from .device import applicability,detect
            if not applicability(r.platforms,env.device or detect())['canApply']:raise Refused('NOT_APPLICABLE')
            matching,conflicts=cli._matching(r,env)
            if matching or conflicts:raise Refused('STATE_UNKNOWN')
        cli.cmd_recipe(ns(id=args[0],action=action),env)
    elif op.startswith('agent-'):
        a=next((a for a in agent_rows(env) if a['id']==args[0]),None)
        if not a or not a['supported']:raise Refused('MISSING')
        action=op.removeprefix('agent-')
        if action in ('connect','revert'):
            if not a['connectable'] or (action=='connect' and not a['installed']):raise Refused('MISSING')
            cli.cmd_agent(ns(agent=args[0],action=action),env)
        else:
            if not a['installed'] or (not a['web_only'] and not a['connected']):raise Refused('MISSING')
            if action=='web':
                if not a['web']:raise Refused('MISSING')
                if env.run([str(Path(__file__).resolve().parents[1]/'bin/raytone-models'),'agent-web',args[0]],dict(os.environ)):raise Refused('FAILED')
            else:
                command=COMMANDS.get(args[0])
                if not command or not shutil.which('omarchy-launch-tui'):raise Refused('MISSING')
                actual=[command]
                if args[0] in ('claude','copilot'):actual=[str(Path(__file__).resolve().parents[1]/'bin/raytone-models'),'agent-exec',args[0]]
                if args[0] in ('pi','omp'):actual += ['--model','raytone/local']
                if args[0]=='openclaw':actual += ['--tui']
                if env.run(['omarchy-launch-tui',*actual],dict(os.environ)):raise Refused('FAILED')
    return {'accepted':True,'message':'操作已返回，请以重新读取的实际状态为准。'}

class Jobs:
    def __init__(self, root=None):
        self.root=Path(root or Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'raytone-models/workbench')
    def path(self,jid):
        if not isinstance(jid,str) or not UUID.fullmatch(jid):raise ValueError('Invalid request ID')
        return self.root/(jid+'.json')
    @contextlib.contextmanager
    def locked(self):
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        with (self.root/'lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX);yield
    def write(self,p,v):
        from .agents import _atomic_write
        _atomic_write(p,(json.dumps(v,ensure_ascii=False)+'\n').encode(),0o600)
    def get(self,jid,full=True):
        from .downloads import _alive
        v=json.loads(self.path(jid).read_text())
        alive=_alive(v)
        try:alive=alive and Path('/proc/'+str(v.get('pid'))+'/stat').read_text().rpartition(')')[2].split()[0]!='Z'
        except (OSError,IndexError):alive=False
        if v['phase']=='running' and not alive:v=v|{'phase':'unknown','message':'任务进程已结束，结果未确认。请重新读取状态；不会自动重试。'}
        out={k:v[k] for k in ('id','operation','phase','message','created','updated','result') if k in v}
        out['updated']=v.get('updated',v['created'])
        if v['operation'] in ('chat','video'):
            request=v['request']
            out.update({k:request[k] for k in ('conversationId','kind','model','params')})
            out['prompt']=request['prompt'] if full else request['prompt'][:160]
            out.update({k:v[k] for k in ('stage','elapsed','generationId','waitStopped','artifact','reasoningChars') if k in v})
            out['text']=v.get('text','')[:32768] if full else ''
            out['textTruncated']=len(v.get('text',''))>32768
        return out
    def submit(self,op,args,jid,spawn=subprocess.Popen):
        from .downloads import _identity
        validate_action(op,args);p=self.path(jid)
        with self.locked():
            if p.exists():
                old=json.loads(p.read_text())
                if (old['operation'],old['args'])!=(op,args):raise ValueError('Request ID already used')
                return self.get(jid)
            # One mutation at a time, including recipe fetch. Reads can run independently.
            for f in self.root.glob('*.json'):
                old=json.loads(f.read_text());j=self.get(old['id'])
                if op not in READS and old['operation'] not in READS and j['phase'] in ('running','unknown'):raise Refused('BUSY')
            v={'id':jid,'operation':op,'args':args,'phase':'running','created':time.time(),'message':'正在处理…'}
            self.write(p,v)
            try:
                proc=spawn([str(Path(__file__).resolve().parents[1]/'bin/raytone-models'),'workbench-worker',jid],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                v.update(pid=proc.pid,ident=_identity(proc.pid));self.write(p,v)
            except OSError:
                v.update(phase='failed',message=MESSAGES['FAILED']);self.write(p,v)
            return self.get(jid)
    def spawn_worker(self,v,spawn=subprocess.Popen):
        from .downloads import _identity
        try:
            proc=spawn([str(Path(__file__).resolve().parents[1]/'bin/raytone-models'),'workbench-worker',v['id']],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            v.update(pid=proc.pid,ident=_identity(proc.pid));self.write(self.path(v['id']),v)
        except OSError:
            v.update(phase='failed',message=MESSAGES['FAILED']);self.write(self.path(v['id']),v)
        return self.get(v['id'])
    def submit_task(self,data,jid,spawn=subprocess.Popen):
        from .tasks import validate
        validate(data);p=self.path(jid)
        with self.locked():
            if p.exists():
                v=json.loads(p.read_text())
                if v.get('request')!=data:raise ValueError('Request ID already used')
                return self.get(jid)
            if any(j['operation'] not in READS and j['phase'] in ('running','unknown') for j in self.recent()):raise Refused('BUSY')
            v={'id':jid,'operation':data['kind'],'args':[],'request':data,'phase':'running','stage':'queued','created':time.time(),'message':'任务已记录，正在核对所选模型。','text':'','waitStopped':False}
            self.write(p,v);return self.spawn_worker(v,spawn)
    def task_list(self,before=''):
        if before:self.path(before)
        values=[j for j in self.recent_all() if j['operation'] in ('chat','video')]
        if before:
            index=next((i for i,j in enumerate(values) if j['id']==before),None)
            if index is None:raise ValueError('Unknown cursor')
            values=values[index+1:]
        return {'schema':1,'tasks':values[:40],'nextCursor':values[39]['id'] if len(values)>40 else ''}
    def recent_all(self):
        if not self.root.exists():return []
        values=[self.get(f.stem,full=False) for f in self.root.glob('*.json')]
        return sorted(values,key=lambda j:j['created'],reverse=True)
    def task_control(self,jid,action,spawn=subprocess.Popen):
        with self.locked():
            self.path(jid);v=json.loads(self.path(jid).read_text())
            if v['operation'] not in ('chat','video'):raise ValueError('Not an inference task')
            if action in ('task-stop-wait','task-rejoin'):
                v['waitStopped']=action=='task-stop-wait';v['updated']=time.time();self.write(self.path(jid),v)
            elif action=='task-refresh':
                current=self.get(jid)
                if v['operation']!='video' or not v.get('generationId') or current['phase'] not in ('unknown','failed'):raise ValueError('No recoverable video task')
                if any(j['id']!=jid and j['phase'] in ('running','unknown') and j['operation'] not in READS for j in self.recent()):raise Refused('BUSY')
                v.update(phase='running',stage='recovering',claimed=False,message='正在读取原视频任务，未重新生成。');self.write(self.path(jid),v)
                return self.spawn_worker(v,spawn)
            else:raise ValueError('Invalid task control')
            return self.get(jid)
    def worker(self,jid,env):
        with self.locked():
            v=json.loads(self.path(jid).read_text())
            if v['phase']!='running' or v.get('claimed'):return
            v['claimed']=True;self.write(self.path(jid),v)
        try:
            from .session_guard import require_unlocked
            require_unlocked()
            if v['operation'] in ('chat','video'):
                from .tasks import run
                run(self,jid,env);return
            result=execute(v['operation'],v['args'],env)
            v.update(phase='done',result=result,message=result.get('message','读取完成。'))
        except (Exception,SystemExit) as e:
            message=str(e);code=next((k for k in MESSAGES if k in message),'NETWORK' if v['operation'] in READS|{'download','recipe-fetch'} else 'FAILED')
            v.update(phase='cancelled' if code=='AUTH_CANCELLED' else 'failed',message=MESSAGES[code])
        with self.locked():self.write(self.path(jid),v)
    def recent(self):
        if not self.root.exists():return []
        files=sorted(self.root.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        values=[self.get(f.stem,full=False) for f in files]
        values.sort(key=lambda j:(j['phase'] in ('running','unknown'),j['created']),reverse=True)
        return values[:30]

def handle(request,env,jobs=None):
    jobs=jobs or Jobs()
    if not isinstance(request,dict) or set(request)-{'op','args','requestId','content'}:raise ValueError('Invalid request')
    op=request.get('op');args=request.get('args',[])
    if 'content' in request and op!='task-create':raise ValueError('Content not allowed')
    if op=='task-create' and args==[]:return jobs.submit_task(request.get('content'),request.get('requestId'))
    if op=='task-capabilities' and args==[]:
        from .tasks import capabilities
        return capabilities(env)
    if op=='activity' and args==[]:return {'protocol':1,'busy':any(j['phase'] in ('running','unknown') and j['operation'] not in READS for j in jobs.recent())}
    if op=='task-list' and isinstance(args,list) and len(args)==1:return jobs.task_list(args[0])
    if op in ('task-stop-wait','task-rejoin','task-refresh') and isinstance(args,list) and len(args)==1:return jobs.task_control(args[0],op)
    if op=='task-artifact' and isinstance(args,list) and len(args)==2:
        from .tasks import artifact
        jobs.path(args[0]);return artifact(jobs,args[0],args[1],env)
    if op=='state' and isinstance(args,list) and len(args)==1:
        return snapshot(args[0],env)|{'jobs':jobs.recent()}
    if op=='job' and isinstance(args,list) and len(args)==1:
        from .tasks import present
        return present(jobs.get(args[0]),jobs,env)
    if op=='ack' and isinstance(args,list) and len(args)==1:
        with jobs.locked():
            j=jobs.get(args[0])
            if j['phase']!='unknown':raise ValueError('Only unknown outcomes need acknowledgement')
            v=json.loads(jobs.path(args[0]).read_text());v.update(phase='acknowledged',message='已确认需人工核对结果，未重新执行操作。');jobs.write(jobs.path(args[0]),v)
        return jobs.get(args[0])
    return jobs.submit(op,args,request.get('requestId'))
