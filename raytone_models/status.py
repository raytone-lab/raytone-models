"""Bounded, read-only connection state; absence is never a ready empty result."""
import json
import socket
from urllib.error import HTTPError
from urllib.request import ProxyHandler, HTTPRedirectHandler, build_opener
from . import connection, system_contract, USER_VERSION


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def router_status(config=None, timeout=2):
    config = config or connection.load()
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(config.internal + '/health', timeout=timeout) as response:
            value = json.loads(response.read(65537))
        if (not isinstance(value, dict) or value.get('kind') != 'raytone-models-router'
                or value.get('schema') != 1 or type(value.get('ready')) is not bool
                or not isinstance(value.get('models'), list)
                or value.get('code') not in ('OK', 'NO_INSTANCE', 'MODEL_UNAVAILABLE')):
            raise ValueError()
        if value['ready'] and (value.get('current') not in value['models'] or value['code'] != 'OK'):
            raise ValueError()
        return value
    except HTTPError as error:
        return {'ready': False, 'code': 'BUSY' if error.code in (429, 503) else 'PORT_CONFLICT'}
    except (TimeoutError, socket.timeout):
        return {'ready': False, 'code': 'TIMEOUT'}
    except ValueError:
        return {'ready': False, 'code': 'PORT_CONFLICT'}
    except OSError:
        return {'ready': False, 'code': 'ROUTER_UNAVAILABLE'}


def workbench_state(state, system):
    if not system['ready']:
        return {'phase': 'setup'}
    if state['code'] == 'NO_INSTANCE':
        return {'phase': 'idle'}
    if state['code'] not in ('OK', 'MODEL_UNAVAILABLE'):
        return {'phase': 'unavailable'}
    from .router import DEFAULT_REGISTRY, instances
    from .spec import INSTANCE_PORTS
    current = state.get('current')
    if not isinstance(current, str) or not current:
        return {'phase': 'unavailable'}
    registered = current in instances(DEFAULT_REGISTRY, INSTANCE_PORTS)
    if registered:
        return {'phase': 'ready' if state['ready'] else 'waiting', 'model': current}
    if state['ready']:
        from .ollama import Ollama
        if any(model['name'] == current for model in Ollama(timeout=1).running()):
            return {'phase': 'ready', 'model': current}
    return {'phase': 'idle'}


def snapshot():
    config = connection.load()
    from .device import detect
    state = router_status(config)
    system = system_contract.identity()
    return {'kind': 'raytone-models', 'schema': 1, 'version': USER_VERSION,
            'cliProtocol': 1, 'internal': config.internal, 'public': config.public,
            'device': detect(), 'router': state, 'system': system,
            'workbench': workbench_state(state, system)}
