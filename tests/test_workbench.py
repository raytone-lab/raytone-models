"""Console integration tests use explicit injected fixtures, never a production flag."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from raytone_models import workbench as w,cli

ID='12345678-1234-4234-8234-123456789abc'
class WorkbenchTests(unittest.TestCase):
    def test_closed_operations_and_parameters(self):
        for op,args in [('exec',['id']),('download',['../x','a'*40,'all files']),('download',['a/b','latest','all']),('search',['x','shell']),('detail',['a/b\n--x','']),('recipe-apply',['--help'])]:
            with self.assertRaises(ValueError):w.validate_action(op,args)
        w.validate_action('download',['a/b','a'*40,'all files'])
    def test_submit_is_durable_deduplicated_and_conflicting_ids_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=w.Jobs(folder);spawn=Mock(return_value=SimpleNamespace(pid=123))
            with patch('raytone_models.downloads._alive',return_value=False):
                first=jobs.submit('detail',['a/b',''],ID,spawn)
                self.assertEqual(jobs.submit('detail',['a/b',''],ID,spawn),first)
                with self.assertRaises(ValueError):jobs.submit('detail',['c/d',''],ID,spawn)
                self.assertEqual(spawn.call_count,1);self.assertEqual(first['phase'],'unknown')
                self.assertEqual(w.Jobs(folder).get(ID)['phase'],'unknown')
    def test_unknown_mutation_is_blocking_until_explicit_ack_no_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=w.Jobs(folder);spawn=Mock(return_value=SimpleNamespace(pid=123))
            jobs.submit('agent-connect',['opencode'],ID,spawn)
            other='22345678-1234-4234-8234-123456789abc'
            with self.assertRaises(w.Refused):jobs.submit('agent-revert',['opencode'],other,spawn)
            j=w.handle({'op':'ack','args':[ID]},None,jobs);self.assertEqual(j['phase'],'acknowledged');self.assertEqual(spawn.call_count,1)
    def test_worker_cancellation_and_errors_are_bounded_and_do_not_leak(self):
        for message,phase in [('AUTH_CANCELLED private-token','cancelled'),('network secret /home/private','failed')]:
            with tempfile.TemporaryDirectory() as folder:
                jobs=w.Jobs(folder);jobs.write(jobs.path(ID),{'id':ID,'operation':'recipe-apply','args':['r'],'phase':'running','created':1,'message':''})
                with patch('raytone_models.session_guard.require_unlocked'),patch.object(w,'execute',side_effect=SystemExit(message)):
                    jobs.worker(ID,None)
                result=jobs.get(ID);self.assertEqual(result['phase'],phase);self.assertNotIn('private',json.dumps(result));self.assertNotIn('secret',json.dumps(result))
    def test_locked_session_never_executes(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=w.Jobs(folder);jobs.write(jobs.path(ID),{'id':ID,'operation':'recipe-fetch','args':['r'],'phase':'running','created':1,'message':''})
            with patch('raytone_models.session_guard.require_unlocked',side_effect=SystemExit('SESSION_LOCKED')),patch.object(w,'execute') as execute:jobs.worker(ID,None)
            execute.assert_not_called();self.assertEqual(jobs.get(ID)['phase'],'failed')
    def test_search_detail_reuse_configured_hub_and_only_project_public_fields(self):
        hub=Mock();hub.search.return_value=[{'id':'a/b','downloads':2,'secret':'s'}];hub.files.return_value=('a'*40,[{'path':'config.json','size':2}])
        env=Mock();env.hub.return_value=hub
        self.assertEqual(w.execute('search',['hello',''],env)['rows'],[{'id':'a/b','downloads':2,'likes':None,'pipeline_tag':None}]);self.assertNotIn('secret',json.dumps(w.execute('detail',['a/b',''],env)))
    def test_download_uses_pinned_revision_and_existing_resumable_downloader(self):
        with patch.object(w.shutil,'which',return_value='/fixture/hf'),patch.object(cli,'cmd_download') as download:
            w.execute('download',['a/b','a'*40,'Q4_K_M'],None)
            a,env=download.call_args.args;self.assertEqual(a.repo,'a/b@'+'a'*40);self.assertEqual(a.variant,'Q4_K_M')
    def test_guard_rejects_busy_unknown_direct_work_and_video_queue(self):
        env=Mock()
        with patch.object(w,'local_json',return_value={'event':'status','active_requests':1}),patch.object(cli,'_registered',return_value=[]):
            with self.assertRaisesRegex(w.Refused,'BUSY'):w.idle(env)
        with patch.object(w,'local_json',return_value={'event':'status','active_requests':0}),patch.object(cli,'_registered',return_value=[{'port':18000,'engine':'vllm'}]),patch('raytone_models.live.counters',return_value=None):
            with self.assertRaisesRegex(w.Refused,'STATE_UNKNOWN'):w.idle(env)
        with patch.object(w,'local_json',side_effect=[{'event':'status','active_requests':0},{'queue_running':[1],'queue_pending':[]}]),patch.object(cli,'_registered',return_value=[{'port':18000,'engine':'comfyui'}]):
            with self.assertRaisesRegex(w.Refused,'BUSY'):w.idle(env)
    def test_recipe_signature_and_platform_refusals_never_start(self):
        env=SimpleNamespace(device={'platform':'unknown'})
        for invalid in (True,False):
            with patch('raytone_models.system_contract.require'),patch.object(w,'idle'),patch.object(cli,'_recipe',side_effect=SystemExit('invalid signature') if invalid else None,return_value=SimpleNamespace(platforms=['thor-t5000'])),patch.object(cli,'cmd_recipe') as apply:
                with self.assertRaises((SystemExit,w.Refused)):w.execute('recipe-apply',['sample'],env)
                apply.assert_not_called()
    def test_partial_recipe_waiting_is_not_ready_and_signature_refusals_reported(self):
        env=Mock();r={'id':'r','state':'ready','running':True,'applicability':{'canApply':True}}
        with patch('raytone_models.status.snapshot',return_value={'system':{'ready':True}}),patch.object(cli,'_instances',return_value=[{'id':'i','ready':False}]),patch.object(cli,'cmd_recipes',return_value={'recipes':[r],'refused':[{}]}),patch.object(cli,'_recipe'),patch.object(cli,'_matching',return_value=({'local':'i'},[])):
            result=w.snapshot('recipes',env);self.assertEqual(result['rows'][0]['phase'],'waiting');self.assertEqual(result['refusedCount'],1)
    def test_prepared_recipe_is_not_a_running_service(self):
        env=Mock();r={'id':'r','state':'ready','running':False,'applicability':{'canApply':True}}
        with patch('raytone_models.status.snapshot',return_value={'system':{'ready':True}}),patch.object(cli,'_instances',return_value=[]),patch.object(cli,'cmd_recipes',return_value={'recipes':[r],'refused':[]}),patch.object(cli,'_recipe'),patch.object(cli,'_matching',return_value=({},[])):
            self.assertEqual(w.snapshot('recipes',env)['rows'][0]['phase'],'prepared')
    def test_worker_receipt_cannot_be_reexecuted(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs=w.Jobs(folder);jobs.write(jobs.path(ID),{'id':ID,'operation':'detail','args':['a/b',''],'phase':'running','created':1,'message':''})
            with patch('raytone_models.session_guard.require_unlocked'),patch.object(w,'execute',return_value={}) as execute:
                jobs.worker(ID,None);jobs.worker(ID,None)
            self.assertEqual(execute.call_count,1)
    def test_not_installed_or_unsupported_agent_cannot_launch(self):
        for entry in ({'id':'opencode','supported':False},{'id':'opencode','supported':True,'installed':False}):
            with patch.object(w,'agent_rows',return_value=[entry]),patch.object(cli,'cmd_agent') as act:
                with self.assertRaises(w.Refused):w.execute('agent-launch',['opencode'],Mock())
                act.assert_not_called()
    def test_no_fixture_toggle_or_new_listener(self):
        source=Path(w.__file__).read_text();self.assertNotIn('RAYTONE_TEST',source);self.assertNotIn('HTTPServer',source)
    def test_signed_recipe_full_lifecycle_with_injected_engine_and_downloader(self):
        from tests import test_cli
        case=test_cli.CliTests('test_models_json');case.setUp()
        try:
            case.signed_recipe();env=case.env
            from tests.test_store import SHA
            snap=env.hf_home/'hub/models--RadixArk--Qwen3.8-27B-NVFP4-BF16-LMHead/snapshots'/SHA
            weight=snap/'m.safetensors';saved=weight.read_bytes();weight.unlink()
            requests=[]
            def download(argv,environ):
                requests.append(argv);weight.write_bytes(saved);return 0
            env.run=download;env.probe=lambda _:False
            def helper(argv,stdin=None):
                if argv==['start']:
                    value=json.loads(stdin);(case.reg/(value['id']+'.json')).write_text(stdin)
                else:(case.reg/(argv[1]+'.json')).unlink()
                return {'ok':True}
            env.helper=helper
            with patch.object(w.shutil,'which',return_value='/fixture/hf'),patch('raytone_models.system_contract.require'),patch.object(w,'idle'),patch('raytone_models.status.snapshot',return_value={'system':{'ready':True}}):
                self.assertEqual(w.snapshot('recipes',env)['rows'][0]['phase'],'missing')
                w.execute('recipe-fetch',['qwen38-27b-coder'],env);self.assertEqual(len(requests),1)
                self.assertEqual(w.snapshot('recipes',env)['rows'][0]['phase'],'prepared')
                w.execute('recipe-apply',['qwen38-27b-coder'],env)
                self.assertEqual(w.snapshot('recipes',env)['rows'][0]['phase'],'waiting')
                env.probe=lambda _:True
                self.assertEqual(w.snapshot('recipes',env)['rows'][0]['phase'],'ready')
                w.execute('recipe-stop',['qwen38-27b-coder'],env)
                self.assertEqual(w.snapshot('recipes',env)['rows'][0]['phase'],'prepared')
        finally:case.tearDown()
    def test_agent_connect_launch_revert_uses_existing_adapter_and_fixed_launcher(self):
        with tempfile.TemporaryDirectory() as folder:
            env=SimpleNamespace(home=Path(folder),state=Path(folder)/'state',run=Mock(return_value=0))
            config=env.home/'.config/opencode/opencode.json';config.parent.mkdir(parents=True);config.write_text('{"theme":"original"}')
            with patch.object(w.shutil,'which',return_value='/fixture/tool'):
                w.execute('agent-connect',['opencode'],env)
                self.assertTrue(next(a for a in w.agent_rows(env) if a['id']=='opencode')['connected'])
                w.execute('agent-launch',['opencode'],env);self.assertEqual(env.run.call_args.args[0],['omarchy-launch-tui','opencode'])
                w.execute('agent-revert',['opencode'],env);self.assertEqual(config.read_text(),'{"theme":"original"}')
