# N1X HF 源修复组合源

2026-11-12。盒子安装版本 `0.2.12-hf-source-om78`，组件身份、固定通用源码及文件摘要见 `manifest.json`。这是对原 om65 特殊组件的增量，保留 N1X、CPU、embedding／music、配方签名者等原有设备适配；不替代独立的系统组件、镜像或权重交付。

## 复原

1. 在独立 Git checkout 检出 `8b44ef0bc8870c9dec7ab008c1263b976f053143`，按 `../om65-2026-11-12/README.md` 和其 manifest 严格复原原 om65 组合源。
2. 核对本 manifest 中五份文件的 `before` 摘要。必须在该独立 Git 工作树根目录运行以下命令；`git rev-parse --show-toplevel` 必须等于当前目录。不要在另一个仓库中的普通子目录直接运行 `git apply`，否则不匹配的路径可能被跳过。
3. 核对补丁 SHA256，再执行：

```sh
git apply --check /absolute/path/to/om78-hf-source-2026-11-12/hf-source.patch
git apply /absolute/path/to/om78-hf-source-2026-11-12/hf-source.patch
python3 - <<'PY'
from pathlib import Path
p = Path('raytone_models/__init__.py')
assert p.read_text() == 'USER_VERSION = "0.2.11-model-list-om65"\n'
p.write_text('USER_VERSION = "0.2.12-hf-source-om78"\n')
PY
```

4. 核对五份文件的 `after` 摘要和原 97 个受管文件；只有这五份应变化。其余文件与 om65 输入逐字节一致。正式用户组件安装后，当前身份应为 manifest 的 `componentId`。

通用功能代码来自 `12edd32c79a47c95546b36dde9c850cd6009a5e7`：统一端点惰性解析、镜像元数据参数兼容、普通和配方下载子进程使用同一源，以及明确错误反馈。字段优先级见主 README；盒子只在原 provider.toml 合并 `[downloads].hf_endpoint = "https://hf-mirror.com"`，不整份替换配置。

更新用户组件需先结束前台对话／视频并关闭 Models，在无请求时维护内部路由，再用正式 `raytone-models-component install` 安装，之后恢复内部路由。后台模型和权重不需要为用户组件重装。原组件作为 previous 保留；配置备份只留设备私有目录，回退前比对期间的合法修改。
