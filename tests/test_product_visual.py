import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from raytone_models import device, cli, store


class DeviceTests(unittest.TestCase):
    def detect(self, name):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'sys/firmware/devicetree/base/model';p.parent.mkdir(parents=True);p.write_text(name)
            with patch('shutil.which',return_value=None):return device.detect(root)

    def test_memory_and_architecture_never_imply_a_platform(self):
        for name in ('', '128GB ARM machine', 'QEMU Virtual Machine'):
            d=self.detect(name);self.assertEqual(d['platform'],'unknown')
            self.assertFalse(device.applicability(['thor-t5000'],d)['canApply'])

    def test_spark_is_distinct_and_generic_thor_does_not_imply_t5000(self):
        spark=self.detect('NVIDIA DGX Spark')
        self.assertEqual(spark['platform'],'dgx-spark')
        self.assertFalse(device.applicability(['thor-t5000'],spark)['canApply'])
        self.assertEqual(self.detect('NVIDIA Jetson AGX Thor Developer Kit')['platform'],'thor-unknown')
        thor=self.detect('NVIDIA Jetson AGX Thor T5000')
        self.assertTrue(device.applicability(['thor-t5000'],thor)['canApply'])
        self.assertIn('不代表',device.applicability(['thor-t5000'],thor)['message'])

    def test_unsupported_apply_stops_before_spec_or_helper(self):
        from types import SimpleNamespace
        recipe=SimpleNamespace(platforms=['thor-t5000'])
        env=SimpleNamespace(device={'platform':'dgx-spark'})
        with patch.object(cli,'_recipe',return_value=recipe),patch.object(cli.recipes,'specs') as specs:
            with self.assertRaisesRegex(SystemExit,'未声明支持'):cli.cmd_recipe(SimpleNamespace(action='apply',id='thor'),env)
            specs.assert_not_called()

    def test_store_permission_error_is_not_an_empty_collection(self):
        with patch.object(Path,'stat',side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):store.list_models('/test/hf')

    def test_standalone_tokens_have_explicit_source_and_palettes(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'app/VisualTokens.js').read_text()
        value=json.loads(source.split('var tokens = ',1)[1])
        self.assertEqual(value['schema'],1);self.assertEqual(len(value['sourceSha256']),64)
        self.assertEqual(value['dark']['canvas'],'#202124')
