"""Read model/platform identity without inferring it from memory or architecture."""
from pathlib import Path
import shutil
import subprocess


def detect(root=Path('/'), run=subprocess.run):
    def read(name):
        try:return (root/name).read_bytes()[:1024].decode(errors='replace').replace('\0',' ').strip()
        except OSError:return ''
    model=read('sys/firmware/devicetree/base/model') or read('proc/device-tree/model') or read('sys/class/dmi/id/product_name')
    compatible=read('sys/firmware/devicetree/base/compatible')
    platform='unknown';name='未知设备'
    if 'jetson' in model.lower() and 'thor' in model.lower():
        platform='thor-t5000' if 't5000' in model.lower() else 'thor-unknown';name='NVIDIA Jetson AGX Thor'+(' T5000' if platform=='thor-t5000' else '（型号待确认）')
    elif 'dgx spark' in model.lower():platform='dgx-spark';name='NVIDIA DGX Spark'
    elif any(s in (model+' '+compatible).lower() for s in ('qemu','dummy-virt','kvm','virtual machine')):name='虚拟机'
    elif model:name=model[:120]
    gpu={'available':None,'name':None,'message':'GPU状态未知：检测工具不可用。'}
    if shutil.which('nvidia-smi'):
        try:
            r=run(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],capture_output=True,text=True,timeout=2)
            names=r.stdout.strip().splitlines()
            gpu={'available':r.returncode==0 and bool(names),'name':names[0][:120] if names else None,
                 'message':'已检测到NVIDIA GPU；引擎运行仍须另行验证。' if r.returncode==0 and names else '未检测到可用的NVIDIA推理环境。'}
        except (OSError,subprocess.TimeoutExpired):gpu['message']='GPU状态读取失败，请重试。'
    return {'platform':platform,'name':name,'gpu':gpu,'source':'system-hardware'}


def applicability(platforms, device):
    declared=list(platforms);platform=device.get('platform','unknown')
    if platform=='unknown':return {'status':'unknown','declared':declared,'canApply':False,'message':'设备平台未知，不能确认此配方适用。'}
    if platform not in declared:return {'status':'unsupported','declared':declared,'canApply':False,'message':'此配方未声明支持当前设备。'}
    return {'status':'matching','declared':declared,'canApply':True,'message':'配方声明平台匹配；不代表已在本机验证。'}
