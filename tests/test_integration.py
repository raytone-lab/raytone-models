import json
import io
from contextlib import redirect_stderr
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from raytone_models import cli, connection, helper, launcher, system_contract, user_component

ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def test_ports_reject_public_pool_and_ambiguous_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'connection.json'
            for port in (8090,18000,18999,True,1,65536):
                path.write_text(json.dumps({'internal_port':port}))
                with self.subTest(port=port),self.assertRaises(ValueError):connection.load(path)
            path.write_text('{}')
            self.assertEqual(connection.load(path).internal,'http://127.0.0.1:19090')

    def test_missing_or_mismatched_system_component_never_invokes_pkexec(self):
        with patch.object(system_contract,'identity',return_value={'ready':False,'message':'mismatch'}), \
             patch('subprocess.run') as run:
            with self.assertRaisesRegex(SystemExit,'mismatch'):cli._pkexec(['stop','existing'])
            run.assert_not_called()

    def test_activation_rechecks_process_identity_before_dispatch(self):
        before={'address':'0x1','pid':2,'stableId':'abc'}
        with patch.object(launcher,'window',return_value={**before,'pid':3}),patch.object(launcher,'run') as run:
            with self.assertRaises(RuntimeError):launcher.activate(before)
            run.assert_not_called()

    def test_internal_helper_requests_also_refuse_an_old_protocol(self):
        with patch.object(system_contract,'require'),patch.object(helper,'unregister') as unregister, \
             patch.object(helper,'_store_from_config') as store,redirect_stderr(io.StringIO()):
            self.assertEqual(helper.main(['--protocol','0','--component-version','old','unregister','keep']),1)
            unregister.assert_not_called();store.assert_not_called()


class UserComponentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)/'home';self.home.mkdir()
        self.env=patch.dict(os.environ,HOME=str(self.home),XDG_DATA_HOME=str(self.home/'.local/share'))
        self.env.start();self.addCleanup(self.env.stop)
        self.component=user_component.Component()

    def test_unknown_command_is_preserved_before_any_entry_changes(self):
        target=self.component.targets['cli'];target.parent.mkdir(parents=True);target.write_text('personal')
        with self.assertRaisesRegex(ValueError,'入口不属于'):self.component.install(ROOT)
        self.assertEqual(target.read_text(),'personal');self.assertFalse(self.component.receipt.exists())
        self.assertFalse(self.component.targets['current'].exists())

    def test_repeat_and_recovery_keep_user_data(self):
        user=self.home/'Documents/中文.txt';user.parent.mkdir();user.write_bytes(b'untouched')
        first=self.component.install(ROOT);self.assertTrue(first['changed'])
        receipt=self.component.receipt.read_bytes()
        self.assertFalse(self.component.install(ROOT)['changed'])
        self.assertEqual(receipt,self.component.receipt.read_bytes())
        # A killed installer after its first real entry replacement.
        before={k:user_component.encoded(p) for k,p in self.component.targets.items()}
        after=dict(before,cli=user_component.file_value('interrupted'))
        journal={'before':before,'after':after,'receipt':user_component.encoded(self.component.receipt)}
        user_component.replace(self.component.pending,user_component.file_value(json.dumps(journal)))
        user_component.replace(self.component.targets['cli'],after['cli'])
        self.assertTrue(self.component.recover()['recovered'])
        self.assertEqual(self.component.receipt.read_bytes(),receipt)
        self.assertEqual(user.read_bytes(),b'untouched')

    def test_changed_managed_entry_is_not_overwritten(self):
        self.component.install(ROOT)
        self.component.targets['cli'].write_text('edited')
        with self.assertRaisesRegex(ValueError,'入口不属于'):self.component.install(ROOT)
        self.assertEqual(self.component.targets['cli'].read_text(),'edited')

    def test_schema_two_and_verified_maintenance_survive_legacy_payload_rollback(self):
        self.component.install(ROOT);first=self.component.read();entry=self.component.targets['maintenance'].read_bytes()
        legacy=Path(self.temp.name)/'legacy';shutil.copytree(ROOT,legacy,ignore=shutil.ignore_patterns('.git','__pycache__'))
        (legacy/'bin/raytone-models-component').unlink()
        (legacy/'raytone_models/__init__.py').write_text('USER_VERSION = "0.2.2-batch3"\n')
        self.component.install(legacy);value=self.component.read()
        self.assertEqual(value['schema'],2);self.assertEqual(value['version'],'0.2.2-batch3')
        self.assertEqual(value['maintenance'],first['current']);self.assertEqual(self.component.targets['maintenance'].read_bytes(),entry)
        self.assertTrue(all(self.component.status()[k] for k in ('filesMatch','releaseVerified','maintenanceVerified')))
        self.component.install(ROOT);self.assertEqual(self.component.read()['current'],first['current'])

    def test_new_reader_recovers_old_four_target_pending_journal(self):
        self.component.install(ROOT)
        keys=set(self.component.targets)-{'maintenance','router'}
        before={k:user_component.encoded(self.component.targets[k]) for k in keys}
        after={**before,'cli':user_component.file_value('interrupted legacy')}
        journal={'before':before,'after':after,'receipt':user_component.encoded(self.component.receipt)}
        user_component.replace(self.component.pending,user_component.file_value(json.dumps(journal)))
        user_component.replace(self.component.targets['cli'],after['cli'])
        self.assertTrue(self.component.recover()['recovered']);self.assertEqual(user_component.encoded(self.component.targets['cli']),before['cli'])

    def test_tampered_release_and_maintenance_are_visible(self):
        self.component.install(ROOT);value=self.component.read()
        (self.component.root/'releases'/value['current']/'raytone_models/cli.py').write_text('edited')
        status=self.component.status();self.assertTrue(status['filesMatch']);self.assertFalse(status['releaseVerified']);self.assertFalse(status['maintenanceVerified'])

    def test_live_update_gate_refuses_gui_and_running_router(self):
        self.component.live=True
        for rows,state in (([{'class':'ai.raytone.Models'}],'inactive'),([], 'active')):
            def run(argv,**kw):return subprocess.CompletedProcess(argv,0,json.dumps(rows) if 'hyprctl' in argv[0] else state,'')
            with patch.object(user_component.subprocess,'run',side_effect=run),self.assertRaises(ValueError):self.component.idle()

    def test_user_version_change_does_not_change_minimal_root_package(self):
        import runpy
        build=runpy.run_path(str(ROOT/'scripts/system-component'))['build']
        source=Path(self.temp.name)/'source';shutil.copytree(ROOT,source,ignore=shutil.ignore_patterns('.git','__pycache__'))
        a=Path(self.temp.name)/'a.tar.gz';b=Path(self.temp.name)/'b.tar.gz';build(source,a)
        (source/'raytone_models/__init__.py').write_text('USER_VERSION = "only-ui-change"\n');build(source,b)
        self.assertEqual(a.read_bytes(),b.read_bytes())
