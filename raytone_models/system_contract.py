"""Refuse privileged mutations unless all system code has a matching root receipt."""
import hashlib
import json
import os
from pathlib import Path
import stat

VERSION = '0.2.0-batch1'
PROTOCOL = 1
ROOT = Path('/usr/lib/raytone-models')


def trusted(path):
    path = Path(path)
    for part in (path, *path.parents):
        s = part.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise ValueError('系统组件路径不是 root 独占管理：' + str(part))
    return path


def identity():
    try:
        manifest = trusted(ROOT / 'component.json')
        value = json.loads(manifest.read_text())
        if (value.get('kind'), value.get('protocol'), value.get('version')) != ('raytone-models-system', PROTOCOL, VERSION):
            raise ValueError('系统组件版本/协议不匹配，未执行模型写操作。')
        files = value.get('files')
        required = {'raytone-models-helper', 'raytone_models/helper.py', 'raytone_models/system_contract.py',
                    'raytone_models/__init__.py', 'raytone_models/spec.py', 'raytone_models/engines.py'}
        if not isinstance(files, dict) or not required <= set(files):
            raise ValueError('系统组件收据不完整。')
        # Reject unrecorded importable code as well as changed code.
        actual = {str(p.relative_to(ROOT)) for p in (ROOT / 'raytone_models').rglob('*') if p.suffix in ('.py', '.pyc', '.so')}
        if not actual <= set(files):
            raise ValueError('系统组件含未登记的 Python 模块。')
        for name, sha in files.items():
            if Path(name).is_absolute() or '..' in Path(name).parts or not isinstance(sha, str):
                raise ValueError('系统组件收据路径无效。')
            path = trusted(ROOT / name)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise ValueError('系统组件摘要不匹配。')
        # The authorization policy and unit must also be fixed root files.
        system_files = value.get('systemFiles', {})
        for name in ('/usr/share/polkit-1/actions/org.raytone.models.policy',
                     '/usr/lib/systemd/system/raytone-engine@.service'):
            path = trusted(name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != system_files.get(name):
                raise ValueError('系统授权策略或引擎 unit 与收据不匹配。')
        return {'ready': True, 'code': 'OK', 'version': VERSION, 'protocol': PROTOCOL}
    except (OSError, ValueError, TypeError, AttributeError) as error:
        return {'ready': False, 'code': 'SYSTEM_COMPONENT_UNAVAILABLE', 'version': VERSION,
                'protocol': PROTOCOL, 'message': str(error)}


def require():
    value = identity()
    if not value['ready']:
        raise SystemExit(value['message'])
