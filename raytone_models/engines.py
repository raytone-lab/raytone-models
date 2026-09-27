"""Engine adapters: a validated Spec becomes the `docker run` argv the privileged helper executes.

The container gets the GPU through CDI, the model store read-only, a per-instance cache it may
write (compile caches, vLLM's packed tables), its port on loopback only, and no host namespaces.
It runs as the dedicated engine user with no capabilities: nothing it writes to the host cache
can be a root-owned setuid file, and the cache belongs to that user alone.
"""
import json

CONTAINER_PORT = 8000


def _engine_args(spec):
    out = []
    for k in sorted(spec.args):
        v = spec.args[k]
        if v is True:
            out.append(f"--{k}")
        elif isinstance(v, (dict, str)) and k.endswith(("-config", "-per-prompt")):
            obj = json.loads(v) if isinstance(v, str) else v
            out += [f"--{k}", json.dumps(obj, separators=(",", ":"), sort_keys=True)]
        else:
            out += [f"--{k}", str(v)]
    return out


def docker_argv(spec, *, store, cache, user, groups):
    uid, gid = user
    if uid == 0 or gid == 0:
        raise ValueError("the engine never runs as root")
    argv = [
        "docker", "run", "--rm", "--name", f"raytone-{spec.id}",
        f"--user={uid}:{gid}",
        *[f"--group-add={g}" for g in groups],
        "--pull=never",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--device=nvidia.com/gpu=all",
        "--shm-size=16g",
        f"--publish=127.0.0.1:{spec.port}:{CONTAINER_PORT}",
        f"--volume={store}:/hf:ro",
        f"--volume={cache}:/cache",
        "--env=HF_HOME=/hf",
        "--env=HF_HUB_OFFLINE=1",
        "--env=HOME=/cache",
        "--env=XDG_CACHE_HOME=/cache",
        "--env=VLLM_CACHE_ROOT=/cache/vllm",
        "--env=TRITON_CACHE_DIR=/cache/triton",
        "--env=TORCHINDUCTOR_CACHE_DIR=/cache/inductor",
        f"--label=org.raytone.models.id={spec.id}",
    ]
    argv += [f"--env={k}={v}" for k, v in sorted(spec.env.items())]
    argv.append(spec.image)
    if spec.engine == "vllm":
        argv += [f"/hf/hub/{spec.model}", "--served-model-name", spec.served_name,
                 "--host", "0.0.0.0", "--port", str(CONTAINER_PORT)]
        argv += _engine_args(spec)
        return argv
    if spec.engine == "sglang":
        # the module rather than an image's entrypoint script: NGC and LMSYS images both have it
        argv += ["python3", "-m", "sglang.launch_server", "--model-path", f"/hf/hub/{spec.model}",
                 "--served-model-name", spec.served_name, "--host", "0.0.0.0", "--port", str(CONTAINER_PORT),
                 "--enable-metrics"]
        argv += _engine_args(spec)
        return argv
    raise ValueError(f"no adapter for engine {spec.engine}")


def health_url(spec):
    return f"http://127.0.0.1:{spec.port}/v1/models"
