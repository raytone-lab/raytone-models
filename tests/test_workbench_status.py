import unittest
from unittest.mock import patch

from raytone_models.status import workbench_state


class WorkbenchStatusTests(unittest.TestCase):
    def test_models_show_readiness_only_for_a_running_instance(self):
        state = {'code': 'OK', 'ready': True, 'current': 'demo'}
        with patch('raytone_models.router.instances', return_value={}), patch('raytone_models.ollama.Ollama') as ollama:
            ollama.return_value.running.return_value = []
            self.assertEqual(workbench_state(state, {'ready': True}), {'phase': 'idle'})
            ollama.return_value.running.return_value = [{'name': 'demo'}]
            self.assertEqual(workbench_state(state, {'ready': True}), {'phase': 'ready', 'model': 'demo'})

    def test_registered_instance_reports_waiting_until_the_router_can_serve_it(self):
        with patch('raytone_models.router.instances', return_value={'demo': 18000}):
            state = {'code': 'MODEL_UNAVAILABLE', 'ready': False, 'current': 'demo'}
            self.assertEqual(workbench_state(state, {'ready': True}), {'phase': 'waiting', 'model': 'demo'})
            self.assertEqual(workbench_state(state, {'ready': False}), {'phase': 'setup'})
            self.assertEqual(workbench_state({'code': 'NO_INSTANCE'}, {'ready': True}), {'phase': 'idle'})
            self.assertEqual(workbench_state({'code': 'TIMEOUT'}, {'ready': True}), {'phase': 'unavailable'})
