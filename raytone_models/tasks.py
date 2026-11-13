"""Durable local chat/video tasks. No listener, cloud fallback or fixture switches.

The browser's history references Jobs receipts; the worker owns inference and
artifacts. Stopping the UI's wait never signals an engine. Video recovery reads
an existing prompt_id, never submits another workflow.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, ProxyHandler, build_opener
from .status import NoRedirect
from . import connection, video

INFERENCE = {'chat','video'}
MAX_TEXT = 131072

class TaskError(ValueError):
    pass


def validate(data):
    from .workbench import UUID
    if not isinstance(data,dict) or set(data)!={'conversationId','kind','model','prompt','messages','params'}:raise ValueError('Invalid task')
    if not isinstance(data['conversationId'],str) or not UUID.fullmatch(data['conversationId']):raise ValueError('Invalid conversation')
    if not isinstance(data['kind'],str) or data['kind'] not in INFERENCE:raise ValueError('Invalid task kind')
    if not isinstance(data['model'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,190}',data['model']) or data['model']=='local':raise ValueError('Select an explicit model')
    if not isinstance(data['prompt'],str) or not data['prompt'].strip() or len(data['prompt'])>8192 or '\0' in data['prompt']:raise ValueError('Invalid prompt')
    msgs=data['messages'];params=data['params']
    if data['kind']=='chat':
        if params!={} or not isinstance(msgs,list) or not 1<=len(msgs)<=20:raise ValueError('Invalid chat')
        for m in msgs:
            if not isinstance(m,dict) or set(m)!={'role','content'} or m['role'] not in ('user','assistant') or not isinstance(m['content'],str) or not m['content'] or len(m['content'])>8192 or '\0' in m['content']:raise ValueError('Invalid message')
        if msgs[-1]!={'role':'user','content':data['prompt']} or sum(len(m['content']) for m in msgs)>24000:raise ValueError('Invalid context')
    elif msgs!=[] or not isinstance(params,dict) or set(params)!={'size','seconds','turbo'} or params['size'] not in video.SIZES or type(params['seconds']) is not int or params['seconds'] not in (3,5,10) or type(params['turbo']) is not bool:raise ValueError('Invalid video parameters')


def http_json(url,timeout=3):
    with build_opener(ProxyHandler({}),NoRedirect()).open(url,timeout=timeout) as r:return json.loads(r.read(65537))


def capabilities(env):
    from . import cli, live
    values=cli._instances(env)
    try:
        h=http_json(connection.load().public.removesuffix('/v1')+'/healthz')
        local=h.get('local') or {};advertised=local.get('models') if local.get('healthy') is True else []
        if not isinstance(advertised,list):advertised=[]
        gateway=True
    except (OSError,ValueError,TypeError):advertised=[];gateway=False
    chat=[];videos=[]
    for x in values:
        entry={'id':x['id'],'name':x['served_name'],'ready':x.get('ready') is True,'current':x.get('current') is True}
        if x.get('chat') is True:chat.append(entry|{'ready':entry['ready'] and x['served_name'] in advertised})
        elif x.get('engine')=='comfyui' and x.get('role')=='video':videos.append(entry)
    return {'schema':1,'chat':chat,'video':videos,'gatewayAvailable':gateway,'videoSizes':env.video_sizes(),
            'knowledgeConfigured':False,'cancelGeneration':False,'message':'仅使用明确选择的本机模型。停止等待不会终止后台生成。'}


def ready_model(kind,name,env):
    from . import cli
    found=[x for x in cli._instances(env) if x.get('served_name')==name and x.get('ready') is True and ((kind=='chat' and x.get('chat') is True) or (kind=='video' and x.get('engine')=='comfyui' and x.get('role')=='video'))]
    if len(found)!=1:raise TaskError('MODEL_NOT_READY')
    if kind=='chat' and not any(x['name']==name and x['ready'] for x in capabilities(env)['chat']):raise TaskError('MODEL_NOT_READY')
    return found[0]


def update(jobs,jid,**fields):
    with jobs.locked():
        value=json.loads(jobs.path(jid).read_text());value.update(fields,updated=time.time());jobs.write(jobs.path(jid),value)


def raw(jobs,jid):return json.loads(jobs.path(jid).read_text())


def run_chat(jobs,jid,env,opener=None):
    data=raw(jobs,jid)['request'];ready_model('chat',data['model'],env)
    # The public router honors this per-request policy without changing stored policy.
    body={'model':data['model'],'messages':data['messages'],'stream':True,'max_tokens':2048,
          'chat_template_kwargs':{'enable_thinking':False},'stream_options':{'include_usage':True}}
    req=Request(connection.load().public+'/chat/completions',json.dumps(body).encode(),
                {'Content-Type':'application/json','X-Raytone-Mode':'local'})
    opener=opener or build_opener(ProxyHandler({}),NoRedirect())
    text='';reasoning=0;terminal=False;t0=time.time()
    update(jobs,jid,stage='connecting')
    try:
        with opener.open(req,timeout=600) as response:
            if 'text/event-stream' not in response.headers.get('Content-Type',''):raise TaskError('INVALID_STREAM')
            while True:
                line=response.readline(262145)
                if not line:break
                if len(line)>262144:raise TaskError('INVALID_STREAM')
                if time.time()-t0>3600:raise TaskError('STREAM_LOST')
                line=line.decode('utf-8').strip()
                if not line.startswith('data:'):continue
                line=line[5:].strip()
                if line=='[DONE]':terminal=True;break
                event=json.loads(line)
                if 'error' in event:raise TaskError('UPSTREAM_FAILED')
                for choice in event.get('choices',[]):
                    delta=choice.get('delta') or {};part=delta.get('content') or '';thinking=delta.get('reasoning_content') or delta.get('reasoning') or ''
                    if not isinstance(part,str) or not isinstance(thinking,str):raise TaskError('INVALID_STREAM')
                    text+=part;reasoning+=len(thinking)
                    if len(text)>MAX_TEXT:raise TaskError('OUTPUT_LIMIT')
                    if choice.get('finish_reason') is not None:terminal=True
                update(jobs,jid,text=text,reasoningChars=reasoning,stage='generating' if text else 'thinking' if reasoning else 'connecting',elapsed=round(time.time()-t0,1))
    except (OSError,ValueError,UnicodeError):
        # Partial output is preserved. Network loss does not establish that the
        # upstream stopped, and the prompt must never be replayed automatically.
        if text or reasoning:raise TaskError('STREAM_LOST') from None
        raise
    if not terminal:raise TaskError('STREAM_LOST')
    if not text.strip():raise TaskError('EMPTY_RESULT')
    update(jobs,jid,phase='done',stage='saved',text=text,message='回复已保存在本机。',elapsed=round(time.time()-t0,1))
    try:artifact(jobs,jid,'text',env)
    except (OSError,ValueError):pass # canonical text is already durable in the receipt


def file_sha256(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def video_root(env):return Path(env.videos_dir)/'Workbench'

def run_video(jobs,jid,env):
    from . import cli
    value=raw(jobs,jid);data=value['request'];p=data['params']
    target=ready_model('video',data['model'],env)
    registered=next((x for x in cli._registered(env) if x.get('id')==target['id']),None)
    if not registered or type(registered.get('port')) is not int or registered['port'] not in cli.spec_mod.INSTANCE_PORTS:raise TaskError('MODEL_NOT_READY')
    if p['size'] not in env.video_sizes():raise TaskError('VIDEO_SIZE_UNAVAILABLE')
    fingerprint=hashlib.sha256(json.dumps(registered,sort_keys=True).encode()).hexdigest()
    if value.get('generationId') and ((value.get('engineId'),value.get('enginePort'))!=(target['id'],registered['port']) or value.get('engineFingerprint')!=fingerprint):raise TaskError('ENGINE_CHANGED')
    update(jobs,jid,engineId=target['id'],enginePort=registered['port'],engineFingerprint=fingerprint,stage='recovering' if value.get('generationId') else 'submitting')
    def emit(event):
        fields={}
        if event.get('prompt_id'):fields['generationId']=str(event['prompt_id'])[:160]
        if event.get('state'):fields['stage']=event['state']
        if 'elapsed' in event:fields['elapsed']=event['elapsed']
        if fields:update(jobs,jid,**fields)
    root=video_root(env);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    work=root/jid;work.mkdir(exist_ok=True,mode=0o700)
    wf=video.workflow(data['prompt'],size=p['size'],seconds=p['seconds'],seed=0,turbo=p['turbo'])
    path=video.generate(f"http://127.0.0.1:{registered['port']}",wf,work,poll=env.video_poll,emit=emit,prompt_id=value.get('generationId'),cancel_on_timeout=False)
    path=Path(path)
    if path.is_symlink() or path.resolve().parent!=work.resolve() or not path.is_file() or path.stat().st_size<12:raise TaskError('SAVE_FAILED')
    with path.open('rb') as stream:
        if stream.read(8)[4:8]!=b'ftyp':raise TaskError('SAVE_FAILED')
    final=root/(jid+'.mp4');os.replace(path,final)
    update(jobs,jid,phase='done',stage='saved',artifact={'kind':'video','name':jid+'.mp4','bytes':final.stat().st_size,'sha256':file_sha256(final)},message='视频已生成并保存在本机。')


def run(jobs,jid,env):
    try:
        data=raw(jobs,jid)['request'];validate(data)
        if data['kind']=='chat':run_chat(jobs,jid,env)
        else:run_video(jobs,jid,env)
    except (Exception,SystemExit) as error:
        value=raw(jobs,jid);code=str(error)
        unknown=code=='STREAM_LOST' or (value.get('generationId') and not isinstance(error,video.VideoError) and code not in ('SAVE_FAILED','VIDEO_SIZE_UNAVAILABLE','ENGINE_CHANGED'))
        # A remote execution_error is known failure; a network error after queue
        # submission is unknown. Only explicit refresh may read that prompt again.
        if isinstance(error,video.VideoError) and ('did not answer' in code or 'no video after' in code):unknown=bool(value.get('generationId'))
        message={'MODEL_NOT_READY':'所选本机模型尚未就绪，未切换模型或重发。','STREAM_LOST':'连接中断，结果未确认；已保留部分输出，不会自动重发。','SAVE_FAILED':'生成结果尚未保存成功，请重新读取原任务。','VIDEO_SIZE_UNAVAILABLE':'当前设备不支持所选视频尺寸。','ENGINE_CHANGED':'原视频实例已改变，未向新实例发送任务。'}.get(code,'任务未完成，请检查本机模型状态；不会自动重发。')
        update(jobs,jid,phase='unknown' if unknown else 'failed',stage='unknown' if unknown else 'failed',message=message)
        if value.get('text'):
            try:artifact(jobs,jid,'text',env)
            except (OSError,ValueError):pass


def artifact(jobs,jid,kind,env):
    value=raw(jobs,jid);observed=jobs.get(jid);value.update(phase=observed['phase'],message=observed['message'])
    if value['operation'] not in INFERENCE or kind not in ('text','video'):raise ValueError('No artifact')
    if kind=='video':
        if value['phase']!='done' or value.get('artifact',{}).get('kind')!='video':raise ValueError('Video not saved')
        p=video_root(env)/(jid+'.mp4');meta=value['artifact']
        if p.is_symlink() or not p.is_file() or p.stat().st_size!=meta['bytes']:raise ValueError('Video unavailable')
        return {'path':str(p),'bytes':p.stat().st_size,'mime':'video/mp4','name':jid+'.mp4'}
    if value['phase']=='running':raise ValueError('Task is still running')
    root=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'raytone/conversations/artifacts';root.mkdir(parents=True,exist_ok=True,mode=0o700)
    p=root/(jid+'.txt');data=value['request']
    content=f"任务 {jid}\n模型 {data['model']}\n状态 {value['phase']}\n\n{data['prompt']}\n\n{value.get('text','')}\n\n{value.get('message','')}\n"
    from .agents import _atomic_write
    _atomic_write(p,content.encode(),0o600)
    return {'path':str(p),'bytes':p.stat().st_size,'mime':'text/plain','name':jid+'.txt'}


def present(value,jobs,env):
    if value.get('kind')=='video' and value.get('artifact'):
        try:artifact(jobs,value['id'],'video',env);value['artifactAvailable']=True
        except (OSError,ValueError):value.update(artifactAvailable=False,message='视频任务已有结果记录，但保存的文件已移除或暂不可读。')
    return value
