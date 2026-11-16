# N1X 用户组件现场差异快照

日期：2026-11-12。该目录保留已安装 `0.2.11-model-list-om65` 用户组件相对纯源码 `8b44ef0bc8870c9dec7ab008c1263b976f053143` 的差异，避免下次用纯仓库组件覆盖已工作的设备适配。此目录不自动参与安装，不改变通用源码的默认行为。

`manifest.json` 记录七个模块的输入／输出 SHA256、补丁摘要与目标组件身份。`user-component-overlay.patch` 保存原字节差异，包含 N1X 识别、本地配方签名者、CPU 限额、embedding／music 接入以及版本后缀。它是现场保留快照，不等于这些扩展已经逐项验收。

## 复原源目录

在独立、干净的工作目录检出上述固定提交；不要在现有部署或后续技术改动上盲目套补丁。将本目录复制到该工作目录之外，使用绝对路径引用。以下假设已经进入固定提交的源码根目录：

```sh
git rev-parse HEAD
git status --porcelain
```

确认 HEAD 为 `8b44ef0bc8870c9dec7ab008c1263b976f053143`，且无待保留改动。应用前核对补丁和七个输入文件：

```sh
python3 - /absolute/path/to/om65-2026-11-12/manifest.json before <<'PY'
import hashlib,json,sys
from pathlib import Path
manifest=Path(sys.argv[1]); data=json.loads(manifest.read_text())
patch=manifest.parent/data['patch']
assert hashlib.sha256(patch.read_bytes()).hexdigest()==data['patchSha256'], 'patch hash mismatch'
for item in data['files']:
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item[sys.argv[2]], item['path']
print('hashes verified:',sys.argv[2])
PY
git apply --check /absolute/path/to/om65-2026-11-12/user-component-overlay.patch
git apply /absolute/path/to/om65-2026-11-12/user-component-overlay.patch
```

把相同 Python 核对命令的最后一个参数 `before` 改为 `after` 再执行，确认七个输出 SHA。任何输入不符就停下对比，不启用 fuzz、不覆盖后续适配。此时得到可供用户组件安装器使用的组合源目录；按仓库正式维护流程安装，不能直接复制到受管 release 目录。

现场组件身份为 `db1b5ca7e68076b8d5252cbe3df4ffc324f30f0d2373c3b6875141094811041c`。本轮另做离线复原并核对该身份；这验证源载荷可重复取得，不是新的实机验收。

## 必须另外交付的内容

系统组件独立于用户组件。现场系统合同显示 `0.2.3-batch5a` 不足以证明 root helper／spec／engines 与通用源码字节一致；需平台适配者提供匹配的系统包与摘要，不能直接以本补丁推定系统层齐备。也不能把这个补丁无审查地装进所有平台的系统组件。

镜像及其 digest、权重／固定 revision、实际配方及签名、root 管理的本地签名者信任、Flint 专用启动适配和默认应用配置均不包含在此快照。现有 [Flint 运行登记权限补丁](../flint-runtime-registry.patch) 另行核对输入 SHA 后使用。不要上传设备的私钥、token 或完整运行配置来补这些缺件。

完整故障归因、装机顺序、状态回读和现场待验项见 RaytoneOS 的 [Spark 现场修复记录](https://github.com/raytone-lab/RaytoneOS/blob/codex/ai-box-productization/docs/field-fixes/2026-11-spark.md)。后续技术改动优先基于实际收据与差异合并，不能仅沿用此日期快照。
