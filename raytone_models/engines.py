"""Engine adapters: a validated Spec becomes the `docker run` argv the privileged helper executes.

The container gets the GPU through CDI, the model store read-only, a per-instance cache it may
write (compile caches, vLLM's packed tables), its port on loopback only, and no host namespaces.
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


def docker_argv(spec, *, store, cache):
    argv = [
        "docker", "run", "--rm", "--name", f"raytone-{spec.id}",
        "--device=nvidia.com/gpu=all",
        "--shm-size=16g",
        f"--publish=127.0.0.1:{spec.port}:{CONTAINER_PORT}",
        f"--volume={store}:/hf:ro",
        f"--volume={cache}:/cache",
        "--env=HF_HOME=/hf",
        "--env=HF_HUB_OFFLINE=1",
        "--env=XDG_CACHE_HOME=/cache",
        "--env=VLLM_CACHE_ROOT=/cache/vllm",
        f"--label=org.raytone.models.id={spec.id}",
    ]
    argv += [f"--env={k}={v}" for k, v in sorted(spec.env.items())]
    argv.append(spec.image)
    if spec.engine == "vllm":
        argv += [f"/hf/hub/{spec.model}", "--served-model-name", spec.served_name,
                 "--host", "0.0.0.0", "--port", str(CONTAINER_PORT)]
        argv += _engine_args(spec)
        return argv
    raise ValueError(f"no adapter for engine {spec.engine}")


def health_url(spec):
    return f"http://127.0.0.1:{spec.port}/v1/models"
