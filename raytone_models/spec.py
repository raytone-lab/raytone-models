"""Instance specs: one model on one engine. The privileged helper runs only what load() accepts.

A spec names an engine from ENGINES, an image pinned by digest from that engine's registries, a
snapshot inside the model store, a port in the instance range, and engine arguments from the
engine's whitelist with typed, bounded values. Nothing else reaches `docker run`: no volumes,
no extra flags, no free-form strings that could carry a second argument.
"""
import dataclasses
import json
import re

INSTANCE_PORTS = range(18000, 19000)
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
WORD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DIGEST_RE = re.compile(r"^(?P<repo>[a-z0-9][a-z0-9._/-]*)@sha256:[0-9a-f]{64}$")
SNAPSHOT_RE = re.compile(r"^models--[A-Za-z0-9_.-]+--[A-Za-z0-9_.-]+/snapshots/[0-9a-f]{40}$")


class SpecError(ValueError):
    pass


def _flag(v):
    return v is True


def _float(lo, hi):
    return lambda v: isinstance(v, float) and lo <= v <= hi


def _int(lo, hi):
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _word(v):
    return isinstance(v, str) and bool(WORD_RE.match(v))


def _choice(*values):
    return lambda v: v in values


def _json_object(v):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return False
    return isinstance(v, dict) and all(isinstance(k, str) for k in v)


def _draft_path(v):
    # the one path an engine takes: a snapshot inside the store the container mounts at /hf
    return isinstance(v, str) and v.startswith("/hf/hub/") and bool(SNAPSHOT_RE.match(v[len("/hf/hub/"):]))


_BIT = re.compile(r"^[01]$")

# Per engine: the image repositories it may come from, its arguments with their checks, and the
# environment variables it may receive.
ENGINES = {
    "vllm": {
        "images": ("vllm/vllm-openai", "nvcr.io/nvidia/vllm"),
        "args": {
            "gpu-memory-utilization": _float(0.05, 0.95),
            "max-model-len": _int(512, 4_194_304),
            "max-num-seqs": _int(1, 1024),
            "max-num-batched-tokens": _int(256, 1_048_576),
            "kv-cache-dtype": _choice("auto", "fp8", "fp8_e4m3", "bfloat16"),
            "quantization": _word,
            "reasoning-parser": _word,
            "tool-call-parser": _word,
            "enable-auto-tool-choice": _flag,
            "enable-prefix-caching": _flag,
            "enforce-eager": _flag,
            "no-enable-flashinfer-autotune": _flag,
            "trust-remote-code": _flag,
            "speculative-config": _json_object,
            "limit-mm-per-prompt": _json_object,
        },
        # each variable by name, with the values it may take (Qwen3.8 Flash Next's PLE table options)
        "env": {"VLLM_PLE_MMAP": re.compile(r"^[01]$"), "VLLM_PLE_SSD": re.compile(r"^[01]$"),
                "VLLM_ALLOW_LONG_MAX_MODEL_LEN": re.compile(r"^[01]$")},
    },
    "sglang": {
        "images": ("nvcr.io/nvidia/sglang", "lmsysorg/sglang"),
        "args": {
            "mem-fraction-static": _float(0.05, 0.95),
            "context-length": _int(512, 4_194_304),
            "max-running-requests": _int(1, 1024),
            "chunked-prefill-size": _int(256, 1_048_576),
            "cuda-graph-max-bs": _int(1, 1024),
            "cuda-graph-max-bs-decode": _int(1, 1024),
            "kv-cache-dtype": _choice("auto", "fp8_e4m3", "fp8_e5m2", "bf16", "bfloat16"),
            "mamba-ssm-dtype": _choice("float16", "bfloat16", "float32"),
            "max-mamba-cache-size": _int(1, 1024),
            "quantization": _word,
            "reasoning-parser": _word,
            "tool-call-parser": _word,
            "random-seed": _int(0, 2**31 - 1),
            "trust-remote-code": _flag,
            "allow-auto-truncate": _flag,
            "enable-fp32-lm-head": _flag,
            "disable-shared-experts-fusion": _flag,
            "disable-radix-cache": _flag,
            "disable-cuda-graph": _flag,
            "enable-linear-replayssm-spec": _flag,
            "linear-replayssm-cache-len": _int(1, 1024),
            "speculative-algorithm": _choice("DSPARK", "NEXTN", "EAGLE", "EAGLE3", "DFLASH"),
            "speculative-draft-model-path": _draft_path,
            "speculative-dspark-block-size": _int(1, 64),
            "speculative-num-steps": _int(1, 64),
            "speculative-eagle-topk": _int(1, 64),
            "speculative-num-draft-tokens": _int(1, 64),
        },
        "env": {"SGLANG_ENABLE_SPEC_V2": _BIT, "SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN": _BIT,
                "SGLANG_JIT_DEEPGEMM_PRECOMPILE": _BIT, "FLASHINFER_DISABLE_VERSION_CHECK": _BIT},
    },
    # video and image generation; the image is built on this machine (engines/comfyui), so it is
    # pinned by its image ID rather than a registry digest
    "comfyui": {
        "images": ("raytone/comfyui",),
        "local": True,
        "args": {
            "gpu-only": _flag,
            "highvram": _flag,
            "lowvram": _flag,
            "disable-smart-memory": _flag,
            "reserve-vram": _float(0.0, 64.0),
        },
        "env": {},
    },
}

FIELDS = ("id", "engine", "image", "model", "served_name", "port", "args", "env")


@dataclasses.dataclass(frozen=True)
class Spec:
    id: str
    engine: str
    image: str
    model: str
    served_name: str
    port: int
    args: dict
    env: dict

    def to_json(self):
        return json.dumps(dataclasses.asdict(self), sort_keys=True, indent=2) + "\n"


def load(data):
    if not isinstance(data, dict) or set(data) - set(FIELDS) or set(FIELDS[:6]) - set(data):
        raise SpecError(f"a spec has exactly the fields {', '.join(FIELDS)}")
    d = {"args": {}, "env": {}, **data}
    if not isinstance(d["id"], str) or not ID_RE.match(d["id"]):
        raise SpecError("id: lowercase letters, digits and dashes, at most 64")
    engine = ENGINES.get(d["engine"])
    if engine is None:
        raise SpecError(f"engine: one of {', '.join(ENGINES)}")
    m = DIGEST_RE.match(d["image"]) if isinstance(d["image"], str) else None
    if not m or m["repo"] not in engine["images"]:
        raise SpecError(f"image: pinned by digest, from {', '.join(engine['images'])}")
    if not isinstance(d["model"], str) or not SNAPSHOT_RE.match(d["model"]):
        raise SpecError("model: a snapshot in the store (models--ORG--NAME/snapshots/COMMIT)")
    if not isinstance(d["served_name"], str) or not NAME_RE.match(d["served_name"]):
        raise SpecError("served_name: letters, digits and ._:- only")
    if not isinstance(d["port"], int) or isinstance(d["port"], bool) or d["port"] not in INSTANCE_PORTS:
        raise SpecError(f"port: {INSTANCE_PORTS.start}-{INSTANCE_PORTS.stop - 1}")
    if not isinstance(d["args"], dict) or not isinstance(d["env"], dict):
        raise SpecError("args and env are objects")
    for k, v in d["args"].items():
        check = engine["args"].get(k)
        if check is None:
            raise SpecError(f"args: {k!r} is not an argument this engine accepts")
        if not check(v):
            raise SpecError(f"args: bad value for {k!r}")
    for k, v in d["env"].items():
        allowed = engine["env"].get(k)
        if allowed is None or not isinstance(v, str) or not allowed.match(v):
            raise SpecError(f"env: {k!r} is not allowed or has a bad value")
    return Spec(**{k: d[k] for k in FIELDS})
