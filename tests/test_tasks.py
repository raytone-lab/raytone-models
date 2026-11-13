"""Explicit local HTTP fixtures. These are not model/GPU inference evidence."""
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from raytone_models import tasks,workbench as w,cli,video
from tests.test_video import FakeComfy

ID='f1234567-1234-4234-8234-123456789abc';CID='c1234567-1234-4234-8234-123456789abc'
def data(kind='chat'):
 return {'conversationId':CID,'kind':kind,'model':'test-model','prompt':'你好','messages':[{'role':'user','content':'你好'}] if kind=='chat' else [],'params':{} if kind=='chat' else {'size':'480p','seconds':3,'turbo':True}}
class Gateway(ThreadingHTTPServer):
 def __init__(self):
  self.requests=[];self.truncated=False;self.hold=None;self.started=threading.Event();outer=self
  class H(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_GET(self):
    body=json.dumps({'local':{'healthy':True,'models':['test-model']}}).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
   def do_POST(self):
    body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));outer.requests.append((body,self.headers.get('X-Raytone-Mode')))
    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
    for obj in [{'choices':[{'delta':{'reasoning_content':'private model reasoning'}}]},{'choices':[{'delta':{'content':'真实夹具正文'}}]}]:
     self.wfile.write(('data: '+json.dumps(obj)+'\n\n').encode());self.wfile.flush()
    outer.started.set()
    if outer.hold:outer.hold.wait(3)
    if not outer.truncated:self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
  super().__init__(('127.0.0.1',0),H);threading.Thread(target=self.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
class TaskTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.jobs=w.Jobs(self.root/'jobs');self.env=SimpleNamespace(videos_dir=self.root/'Videos/Raytone',video_sizes=lambda:['480p'],video_poll=.001)
  self.addCleanup(self.tmp.cleanup)
 def seed(self,kind='chat'):
  self.jobs.write(self.jobs.path(ID),{'id':ID,'operation':kind,'args':[],'request':data(kind),'phase':'running','created':1,'message':'starting','text':'','waitStopped':False})
 def gateway(self):
  g=Gateway();self.addCleanup(g.server_close);self.addCleanup(g.shutdown);return g
 def chat_patches(self,g):
  return (patch.object(cli,'_instances',return_value=[{'id':'test','served_name':'test-model','chat':True,'ready':True}]),patch.object(tasks.connection,'load',return_value=SimpleNamespace(public=f'http://127.0.0.1:{g.server_port}/v1')))
 def test_closed_payload_no_references_cloud_or_generic_commands(self):
  for modify in (lambda d:d.update(model='local'),lambda d:d.update(refs=['fake']),lambda d:d.update(kind='exec'),lambda d:d['messages'].append({'role':'system','content':'bad'})):
   d=data();modify(d)
   with self.assertRaises(ValueError):tasks.validate(d)
  tasks.validate(data('video'))
 def test_task_creation_is_durable_and_duplicate_receipt_does_not_spawn_again(self):
  spawn=Mock(return_value=SimpleNamespace(pid=123));first=self.jobs.submit_task(data(),ID,spawn)
  self.assertEqual(self.jobs.submit_task(data(),ID,spawn)['id'],ID);self.assertEqual(spawn.call_count,1)
  self.assertEqual(w.Jobs(self.jobs.root).get(ID)['phase'],'unknown')
  other=data();other['prompt']='changed';other['messages'][-1]['content']='changed'
  with self.assertRaises(ValueError):self.jobs.submit_task(other,ID,spawn)
 def test_chat_stream_uses_public_gateway_exact_model_and_local_only_header(self):
  self.seed();g=self.gateway();a,b=self.chat_patches(g)
  with a,b:tasks.run(self.jobs,ID,self.env)
  result=self.jobs.get(ID);self.assertEqual(result['phase'],'done');self.assertEqual(result['text'],'真实夹具正文');self.assertGreater(result['reasoningChars'],0)
  self.assertEqual(g.requests[0][0]['model'],'test-model');self.assertEqual(g.requests[0][1],'local');self.assertEqual(len(g.requests),1)
  self.assertNotIn('private model reasoning',self.jobs.path(ID).read_text())
  with patch.dict('os.environ',XDG_DATA_HOME=str(self.root/'data')):
   asset=tasks.artifact(self.jobs,ID,'text',self.env);self.assertIn('真实夹具正文',Path(asset['path']).read_text())
 def test_truncated_stream_is_unknown_and_preserves_partial_output_never_retries(self):
  self.seed();g=self.gateway();g.truncated=True;a,b=self.chat_patches(g)
  with a,b:tasks.run(self.jobs,ID,self.env)
  result=self.jobs.get(ID);self.assertEqual(result['phase'],'unknown');self.assertEqual(result['text'],'真实夹具正文');self.assertEqual(len(g.requests),1)
 def test_stop_wait_does_not_cancel_and_late_result_is_saved(self):
  self.seed();g=self.gateway();g.hold=threading.Event();a,b=self.chat_patches(g)
  with a,b:
   thread=threading.Thread(target=tasks.run,args=(self.jobs,ID,self.env));thread.start();self.assertTrue(g.started.wait(2))
   self.jobs.task_control(ID,'task-stop-wait');self.assertEqual(json.loads(self.jobs.path(ID).read_text())['phase'],'running')
   g.hold.set();thread.join(3);self.assertFalse(thread.is_alive())
  result=self.jobs.get(ID);self.assertEqual(result['phase'],'done');self.assertTrue(result['waitStopped']);self.assertEqual(len(g.requests),1)
 def test_unready_selected_model_fails_without_calling_another_model(self):
  self.seed()
  with patch.object(cli,'_instances',return_value=[]),patch.object(tasks,'http_json') as network:tasks.run(self.jobs,ID,self.env)
  self.assertEqual(self.jobs.get(ID)['phase'],'failed');network.assert_not_called()
 def comfy(self):
  server=FakeComfy();server.view_data=b'\x00\x00\x00\x18ftypisom0000000000000000';self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  return server
 def video_patches(self,server):
  item={'id':'vid','served_name':'test-model','engine':'comfyui','role':'video','port':server.server_port,'ready':True,'chat':False}
  return patch.object(cli,'_instances',return_value=[item]),patch.object(cli,'_registered',return_value=[item]),patch.object(cli.spec_mod,'INSTANCE_PORTS',(server.server_port,))
 def test_video_generates_once_saves_real_bytes_and_exports_only_approved_asset(self):
  self.seed('video');server=self.comfy();a,b,c=self.video_patches(server)
  with a,b,c:tasks.run(self.jobs,ID,self.env)
  value=self.jobs.get(ID);self.assertEqual(value['phase'],'done');self.assertEqual(value['generationId'],'p-1');self.assertEqual(len(server.prompts),1)
  asset=tasks.artifact(self.jobs,ID,'video',self.env);self.assertEqual(Path(asset['path']).read_bytes(),server.view_data)
  Path(asset['path']).unlink();self.assertFalse(tasks.present(self.jobs.get(ID),self.jobs,self.env)['artifactAvailable'])
 def test_unknown_video_recovers_original_prompt_without_posting_or_interrupting_again(self):
  self.seed('video');server=self.comfy();a,b,c=self.video_patches(server);original=video._call
  def fail_history(base,path,*args,**kw):
   if path.startswith('/history/'):raise OSError('connection lost')
   return original(base,path,*args,**kw)
  with a,b,c:
   with patch.object(video,'_call',side_effect=fail_history):tasks.run(self.jobs,ID,self.env)
   self.assertEqual(self.jobs.get(ID)['phase'],'unknown');self.assertEqual(len(server.prompts),1)
   self.jobs.task_control(ID,'task-refresh',Mock(return_value=SimpleNamespace(pid=123)))
   with patch('raytone_models.session_guard.require_unlocked'):self.jobs.worker(ID,self.env)
  self.assertEqual(self.jobs.get(ID)['phase'],'done');self.assertEqual(len(server.prompts),1);self.assertFalse(any(p in ('/queue','/interrupt') for p,_ in server.posts))
 def test_invalid_saved_video_never_reports_completion(self):
  self.seed('video');server=self.comfy();server.view_data=b'not an mp4';a,b,c=self.video_patches(server)
  with a,b,c:tasks.run(self.jobs,ID,self.env)
  self.assertNotEqual(self.jobs.get(ID)['phase'],'done')
  with self.assertRaises(ValueError):tasks.artifact(self.jobs,ID,'video',self.env)
 def test_context_and_long_output_are_bounded_without_erasing_saved_text(self):
  d=data();d['messages']=[{'role':'user','content':'x'*8192}]*4
  with self.assertRaises(ValueError):tasks.validate(d)
  self.seed();v=json.loads(self.jobs.path(ID).read_text());v.update(phase='done',text='x'*50000);self.jobs.write(self.jobs.path(ID),v)
  self.assertEqual(len(self.jobs.get(ID)['text']),32768);self.assertTrue(self.jobs.get(ID)['textTruncated']);self.assertEqual(len(json.loads(self.jobs.path(ID).read_text())['text']),50000)
