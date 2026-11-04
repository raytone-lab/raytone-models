import base64
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from raytone_models import helper,session_guard,spec
from tests.test_spec import good

ROOT=Path(__file__).resolve().parents[1]
loader=importlib.machinery.SourceFileLoader('system_installer',str(ROOT/'scripts/system-component'))
module_spec=importlib.util.spec_from_loader(loader.name,loader);installer=importlib.util.module_from_spec(module_spec);loader.exec_module(installer)


class SystemComponentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'root';self.root.mkdir()
        self.calls=[]
        self.c=installer.Installer(self.root,os.getuid(),self.fake_run)
        self.root=self.c.root
        self.bundle=self.base/'system.tar.gz';installer.build(ROOT,self.bundle)
        self.files,self.meta=installer.read_bundle(self.bundle)

    def fake_run(self, argv, **kwargs):
        self.calls.append(argv);return subprocess.CompletedProcess(argv,0,'','')

    def test_reproducible_minimal_bundle_and_repeat_rollback_preserve_data(self):
        other=self.base/'repeat.tar.gz';installer.build(ROOT,other)
        self.assertEqual(self.bundle.read_bytes(),other.read_bytes())
        self.assertNotIn('usr/bin/raytone-models',self.files)
        self.assertFalse(any('rules.d' in n for n in self.files))
        self.assertTrue(self.c.install(self.files,self.meta)['changed'])
        self.assertFalse(self.c.install(self.files,self.meta)['changed'])
        model=self.root/'var/lib/raytone-models/hf/hub/user-model';model.parent.mkdir(parents=True);model.write_bytes(b'model-data')
        self.c.rollback()
        self.assertEqual(model.read_bytes(),b'model-data');self.assertIsNone(self.c.read())
        self.assertFalse(any(self.root.joinpath(n).exists() for n in installer.NAMES))

    def test_unknown_file_and_writable_parent_refuse_before_changes(self):
        p=self.root/'usr/lib/raytone-models/raytone-models-helper';p.parent.mkdir(parents=True);p.write_text('foreign')
        with self.assertRaisesRegex(ValueError,'未覆盖'):self.c.install(self.files,self.meta)
        self.assertEqual(p.read_text(),'foreign');self.assertFalse(self.c.pending.exists())
        p.unlink();p.parent.chmod(0o777)
        with self.assertRaisesRegex(ValueError,'独占管理'):self.c.install(self.files,self.meta)

    def test_active_engine_blocks_updates_and_keeps_receipt(self):
        self.c.install(self.files,self.meta);before=self.c.receipt.read_bytes()
        altered=dict(self.files);key=next(iter(altered));altered[key]={**altered[key],'data':base64.b64encode(b'new').decode()}
        self.c.run=lambda argv,**kw:subprocess.CompletedProcess(argv,0,'raytone-engine@keep.service active','')
        with self.assertRaisesRegex(ValueError,'运行中'):self.c.install(altered,self.meta)
        self.assertEqual(self.c.receipt.read_bytes(),before);self.assertFalse(self.c.pending.exists())

    def test_partial_real_replacement_recovers_without_touching_unrelated_files(self):
        old={n:None for n in installer.NAMES}
        self.c.write_json(self.c.pending,{'before':old,'after':self.files,'receipt':None})
        n=sorted(installer.NAMES)[0];self.c.write(self.root/n,self.files[n])
        marker=self.root/'unrelated';marker.write_bytes(b'keep')
        self.assertTrue(self.c.recover()['recovered'])
        self.assertFalse((self.root/n).exists());self.assertEqual(marker.read_bytes(),b'keep')

    def test_changed_partial_target_is_not_overwritten_on_recovery(self):
        self.c.write_json(self.c.pending,{'before':{n:None for n in installer.NAMES},'after':self.files,'receipt':None})
        n=sorted(installer.NAMES)[0];p=self.root/n;p.parent.mkdir(parents=True);p.write_bytes(b'external-edit')
        with self.assertRaisesRegex(ValueError,'另外修改'):self.c.recover()
        self.assertEqual(p.read_bytes(),b'external-edit');self.assertTrue(self.c.pending.exists())


class PrivilegedBoundaryTests(unittest.TestCase):
    def test_runtime_missing_image_and_gpu_never_mutates(self):
        for fail,expected in [('info','DOCKER_UNAVAILABLE'),('image','IMAGE_MISSING'),('cdi','GPU_UNAVAILABLE')]:
            seen=[]
            def run(argv,**kw):
                seen.append(argv)
                bad=fail in argv
                return subprocess.CompletedProcess(argv,1 if bad else 0,'' if bad else ('nvidia.com/gpu=all' if 'cdi' in argv else 'ok'),'')
            with self.subTest(fail=fail),self.assertRaisesRegex(helper.HelperError,expected):helper.runtime_preflight(spec.load(good()),run)
            self.assertFalse(any('start' in a or 'stop' in a or 'pull' in a for a in seen))

    def test_locked_pkexec_subject_is_refused_after_authentication(self):
        def run(argv,**kw):
            return subprocess.CompletedProcess(argv,0,'4\n' if 'show-user' in argv else 'User=1000\nActive=yes\nRemote=no\nLockedHint=yes\n','')
        with self.assertRaisesRegex(helper.HelperError,'SESSION_LOCKED'):helper.check_subject({'PKEXEC_UID':'1000'},run)

    def test_native_lock_is_checked_as_caller_when_logind_hint_is_clear(self):
        import types
        for native,denied in (({'locked':False},False),({'locked':False,'pending':True},True),({'locked':True},True),({},True)):
            seen=[]
            def run(argv,**kw):
                seen.append(argv)
                output=('4\n' if 'show-user' in argv else 'User=1000\nActive=yes\nRemote=no\nLockedHint=no\n' if 'show-session' in argv else json.dumps(native))
                return subprocess.CompletedProcess(argv,0,output,'')
            with patch.object(helper.pwd,'getpwuid',return_value=types.SimpleNamespace(pw_name='fixture-user',pw_dir='/home/fixture-user')):
                if denied:
                    with self.assertRaisesRegex(helper.HelperError,'SESSION_LOCKED'):helper.check_subject({'PKEXEC_UID':'1000'},run)
                else:helper.check_subject({'PKEXEC_UID':'1000'},run)
            self.assertEqual(seen[-1][:6],['/usr/bin/runuser','-u','fixture-user','--','/usr/bin/env','-i'])

    def test_native_lock_unknown_and_secure_pending_refuse_user_action(self):
        for value in ({'locked':False,'pending':True},{'locked':True},{'wrong':False}):
            with patch('shutil.which',return_value='/usr/bin/omarchy-shell'):
                run=lambda *a,**kw:subprocess.CompletedProcess(a,0,json.dumps(value),'')
                with self.assertRaises(SystemExit):session_guard.require_unlocked(run)


if __name__=='__main__':unittest.main()
