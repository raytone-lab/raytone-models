"""Product connection contract; loading it never changes a running provider."""
from dataclasses import dataclass
import json
from pathlib import Path

CONFIG = Path('/etc/raytone-models/connection.json')


@dataclass(frozen=True)
class Connection:
    internal_port: int = 19090
    public_port: int = 8090

    @property
    def internal(self):
        return f'http://127.0.0.1:{self.internal_port}'

    @property
    def public(self):
        return f'http://127.0.0.1:{self.public_port}/v1'


def load(path=CONFIG):
    try:
        value = json.loads(Path(path).read_text())
    except FileNotFoundError:
        value = {}
    except (OSError, ValueError) as error:
        raise ValueError('模型路由配置无法读取。') from error
    if not isinstance(value, dict) or set(value) - {'schema', 'internal_port', 'public_port'} or value.get('schema', 1) != 1:
        raise ValueError('模型路由配置版本或字段无效。')
    internal, public = value.get('internal_port', 19090), value.get('public_port', 8090)
    if type(internal) is not int or not 1024 <= internal <= 65535 or 18000 <= internal <= 18999 or internal == public:
        raise ValueError('Models 内部端口必须避开公共入口和实例端口池。')
    if type(public) is not int or public != 8090:
        raise ValueError('OS 公共入口固定为 8090。')
    return Connection(internal, public)
