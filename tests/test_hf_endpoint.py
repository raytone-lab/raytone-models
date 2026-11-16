import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from raytone_models import hf, cli


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = self.home / '.config/raytone/provider.toml'
        self.config.parent.mkdir(parents=True)

    def test_precedence_and_path_override(self):
        self.assertEqual(hf.resolve_endpoint(home=self.home, environ={}), hf.DEFAULT_ENDPOINT)
        self.config.write_text('[downloads]\nhf_endpoint="https://hf-mirror.com/"\n')
        self.assertEqual(hf.resolve_endpoint(home=self.home, environ={}), 'https://hf-mirror.com')
        self.assertEqual(hf.resolve_endpoint(home=self.home, environ={'HF_ENDPOINT':'https://environment.example'}), 'https://environment.example')
        self.assertEqual(hf.resolve_endpoint('https://explicit.example', home=self.home, environ={'HF_ENDPOINT':'invalid'}), 'https://explicit.example')
        alternate = self.home/'other.toml'
        alternate.write_text('[downloads]\nhf_endpoint="https://other.example"\n')
        self.assertEqual(hf.resolve_endpoint(home=self.home, environ={'RAYTONE_PROVIDER_CONFIG':str(alternate)}), 'https://other.example')

    def test_invalid_config_never_breaks_local_commands(self):
        self.config.write_text('[downloads\ninvalid')
        with patch.dict(os.environ, {'HF_ENDPOINT':'','RAYTONE_PROVIDER_CONFIG':str(self.config)}):
            env = cli.Env(home=self.home, hf_home=self.home/'hf', engines={}, recipe_dirs=[])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['engines','--json'], env=env), 0)
            with self.assertRaises(hf.HubError): env.hub()
            env.hf_endpoint = 'https://explicit.example'
            self.assertEqual(env.hub_endpoint(), 'https://explicit.example')

    def test_invalid_endpoints_are_rejected_without_echoing_secrets(self):
        for value in ('http://hf-mirror.com', 'https://user:secret@example.com',
                      'https://example.com?token=secret', 'https://example.com/#secret',
                      'https://example.com:invalid', 'https://', 3):
            with self.subTest(value=value), self.assertRaises(hf.HubError) as caught:
                hf.validate_endpoint(value)
            self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(hf.validate_endpoint('http://127.0.0.1:1234'), 'http://127.0.0.1:1234')

    def test_mirror_compact_query_preserves_search_and_revision(self):
        hub = hf.Hub('https://hf-mirror.com')
        with patch.object(hub, '_get', return_value=[{'id':'repo/model','tags':['gguf']}]) as get:
            self.assertTrue(hub.search('qwen',kind='video',limit=7)[0]['gguf'])
            self.assertEqual(get.call_args.args[1], {'search':'qwen','sort':'downloads','direction':'-1','limit':'7','pipeline_tag':'text-to-video'})
        with patch.object(hub, '_get', return_value={'sha':'a'*40}), patch.object(hub, '_get_all', return_value=[]) as tree:
            self.assertEqual(hub.files('repo/model')[0], 'a'*40)
            self.assertIn('a'*40, tree.call_args.args[0])
        official = hf.Hub()
        with patch.object(official,'_get',return_value=[]) as get:
            official.search('qwen')
            self.assertIn('expand[]',get.call_args.args[1])

    def test_http_errors_remain_distinct_and_no_cross_source_retry(self):
        for code in (401,403,404,429,502,503):
            hub=hf.Hub('https://hf-mirror.com')
            error=urllib.error.HTTPError(hub.endpoint,code,'test',{},None)
            with patch.object(hub.opener,'open',side_effect=error) as opened:
                with self.assertRaisesRegex(hf.HubError,str(code)): hub.search('test')
                self.assertEqual(opened.call_count,1)

    def test_invalid_search_data_is_not_an_empty_success(self):
        hub=hf.Hub()
        for value in ({'error':'gateway'},[{}],['wrong']):
            with patch.object(hub,'_get',return_value=value),self.assertRaises(hf.HubError):hub.search('test')

    def test_download_environment_keeps_source_and_only_explicit_token(self):
        with patch.dict(os.environ, {'HF_ENDPOINT':'https://wrong.example','HF_TOKEN':'ambient-secret','HTTPS_PROXY':'http://127.0.0.1:8888'}):
            env=hf.download_environment(self.home/'hf','https://hf-mirror.com')
            self.assertEqual(env['HF_ENDPOINT'],'https://hf-mirror.com')
            self.assertEqual(env['HTTPS_PROXY'],'http://127.0.0.1:8888')
            self.assertNotIn('HF_TOKEN',env)
            self.assertEqual(hf.download_environment(self.home/'hf','https://hf-mirror.com','chosen')['HF_TOKEN'],'chosen')
