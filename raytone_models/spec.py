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
    return isinstance(v, str) and bool(WORD_RE.fullmatch(v))


def _choice(*values):
    return lambda v: v in values


# a GGUF file inside the model's snapshot: path components that start with a letter, digit or _
# (so never "..", never an option), ending in .gguf
GGUF_FILE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*\.gguf$")


def _gguf_file(v):
    return isinstance(v, str) and len(v) <= 255 and bool(GGUF_FILE_RE.fullmatch(v))


def _draft_path(v):
    # the one path an engine takes: a snapshot inside the store the container mounts at /hf
    return isinstance(v, str) and v.startswith("/hf/hub/") and bool(SNAPSHOT_RE.fullmatch(v[len("/hf/hub/"):]))


_BIT = re.compile(r"^[01]$")

def _bool(v):
    return isinstance(v, bool)


def _schema(fields):
    """A JSON object (or a string holding one) with only these keys, each passing its check: vLLM
    reads paths and importable names from some of its config objects, so no free-form ones."""
    def check(v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                return False
        return isinstance(v, dict) and all(k in fields and fields[k](x) for k, x in v.items())
    return check


SPECULATIVE = _schema({"method": _choice("mtp", "dflash", "eagle", "eagle3", "ngram", "draft_model"),
                       "num_speculative_tokens": _int(1, 32), "model": lambda v: _draft_path(v),
                       "use_local_argmax_reduction": _bool, "disable_eagle_block_drop": _bool,
                       "index_share_for_mtp_iteration": _bool})
COMPILATION = _schema({"mode": _int(0, 3),
                       "cudagraph_mode": _choice("NONE", "PIECEWISE", "FULL", "FULL_DECODE_ONLY", "FULL_AND_PIECEWISE")})
ENGRAM = _schema({"cpu_offload": _bool, "embedding_across_dp": _bool, "dp_shared_memory": _bool})
LIMIT_MM = _schema({"image": _int(0, 64), "video": _int(0, 64), "audio": _int(0, 64)})

# Per engine: the image repositories it may come from, its arguments with their checks, and the
# environment variables it may receive.
ENGINES = {
    "vllm": {
        # raytone/vllm-NAME: a vLLM image built on this machine (with a model's own patches, say)
        "images": ("vllm/vllm-openai", "nvcr.io/nvidia/vllm", "raytone/vllm-*"),
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
            "speculative-config": SPECULATIVE,
            "limit-mm-per-prompt": LIMIT_MM,
            # Qwen3.8 Flash Next's single-device lane
            "engram-config": ENGRAM,
            "compilation-config": COMPILATION,
            "kv-cache-memory-bytes": lambda v: isinstance(v, str) and bool(re.fullmatch(r"[1-9][0-9]{0,3}[MG]", v)),
            "mamba-ssm-cache-dtype": _choice("auto", "float16", "bfloat16", "float32"),
            "load-format": _choice("auto", "safetensors"),
            "safetensors-load-strategy": _choice("lazy", "eager"),
            "enable-chunked-prefill": _flag,
            "enable-prompt-tokens-details": _flag,
            "distributed-executor-backend": _choice("mp", "uni"),
        },
        # each variable by name, with the values it may take (Qwen3.8 Flash Next's PLE table options)
        "env": {"VLLM_PLE_MMAP": re.compile(r"^[01]$"), "VLLM_PLE_SSD": re.compile(r"^[01]$"),
                "VLLM_ALLOW_LONG_MAX_MODEL_LEN": re.compile(r"^[01]$"),
                # paths only inside the instance's own cache, or files a local image put in /opt/raytone
                "VLLM_PLE_MMAP_DIR": re.compile(r"/cache(/[A-Za-z0-9_][A-Za-z0-9_.-]*)+"),
                "VLLM_FLASHINFER_AUTOTUNE_CACHE_DIR": re.compile(r"/cache(/[A-Za-z0-9_][A-Za-z0-9_.-]*)+"),
                "VLLM_MTP_DRAFT_VOCAB": re.compile(r"/opt/raytone/[A-Za-z0-9_][A-Za-z0-9_.-]*"),
                "VLLM_PLE_MMAP_ADVICE": re.compile(r"[01]"), "VLLM_USE_V2_MODEL_RUNNER": re.compile(r"[01]"),
                "MAX_JOBS": re.compile(r"[1-9][0-9]?"), "FLASHINFER_NVCC_THREADS": re.compile(r"[1-9][0-9]?")},
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
    # GGUF models; llama.cpp built on this machine with CUDA 13.0 for sm_110 (engines/llamacpp)
    "llamacpp": {
        "images": ("raytone/llamacpp",),
        "local": True,
        "requires": ("model-file",),
        "args": {
            "model-file": _gguf_file,
            "mmproj-file": _gguf_file,
            "ctx-size": _int(512, 4_194_304),
            "n-gpu-layers": _int(0, 999),
            "parallel": _int(1, 64),
            "batch-size": _int(32, 65536),
            "ubatch-size": _int(32, 65536),
            "flash-attn": _choice("on", "off", "auto"),
            "cache-type-k": _choice("f16", "bf16", "q8_0", "q4_0"),
            "cache-type-v": _choice("f16", "bf16", "q8_0", "q4_0"),
            "reasoning-format": _choice("none", "deepseek", "auto"),
            "jinja": _flag,
            "no-mmap": _flag,
        },
        "env": {},
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

FIELDS = ("id", "engine", "image", "model", "served_name", "port", "args", "env", "memory_gib")
LOCAL_REPO_RE = re.compile(r"raytone/[a-z0-9][a-z0-9.-]*")


def is_local(image):
    """An image built on this machine (raytone/...), run by its image ID."""
    return isinstance(image, str) and bool(LOCAL_REPO_RE.fullmatch(image.split("@", 1)[0]))


def _image_allowed(repo, images):
    for pattern in images:
        if pattern.endswith("*"):
            if repo.startswith(pattern[:-1]) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", repo[len(pattern) - 1:]):
                return True
        elif repo == pattern:
            return True
    return False


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
    memory_gib: int = None      # a hard memory limit for the container, without swap

    def to_json(self):
        return json.dumps(dataclasses.asdict(self), sort_keys=True, indent=2) + "\n"


def load(data):
    if not isinstance(data, dict) or set(data) - set(FIELDS) or set(FIELDS[:6]) - set(data):
        raise SpecError(f"a spec has exactly the fields {', '.join(FIELDS)}")
    d = {"args": {}, "env": {}, "memory_gib": None, **data}
    if not isinstance(d["id"], str) or not ID_RE.fullmatch(d["id"]):
        raise SpecError("id: lowercase letters, digits and dashes, at most 64")
    engine = ENGINES.get(d["engine"])
    if engine is None:
        raise SpecError(f"engine: one of {', '.join(ENGINES)}")
    m = DIGEST_RE.fullmatch(d["image"]) if isinstance(d["image"], str) else None
    if not m or not _image_allowed(m["repo"], engine["images"]):
        raise SpecError(f"image: pinned by digest, from {', '.join(engine['images'])}")
    if not isinstance(d["model"], str) or not SNAPSHOT_RE.fullmatch(d["model"]):
        raise SpecError("model: a snapshot in the store (models--ORG--NAME/snapshots/COMMIT)")
    if not isinstance(d["served_name"], str) or not NAME_RE.fullmatch(d["served_name"]):
        raise SpecError("served_name: letters, digits and ._:- only")
    if d["served_name"] == "local":
        raise SpecError("served_name: local is the router's name for the current model")
    if not isinstance(d["port"], int) or isinstance(d["port"], bool) or d["port"] not in INSTANCE_PORTS:
        raise SpecError(f"port: {INSTANCE_PORTS.start}-{INSTANCE_PORTS.stop - 1}")
    mem = d["memory_gib"]
    if mem is not None and (not isinstance(mem, int) or isinstance(mem, bool) or not 8 <= mem <= 128):
        raise SpecError("memory_gib: 8-128, or none")
    if not isinstance(d["args"], dict) or not isinstance(d["env"], dict):
        raise SpecError("args and env are objects")
    for k, v in d["args"].items():
        check = engine["args"].get(k)
        if check is None:
            raise SpecError(f"args: {k!r} is not an argument this engine accepts")
        if not check(v):
            raise SpecError(f"args: bad value for {k!r}")
    for k in engine.get("requires", ()):
        if k not in d["args"]:
            raise SpecError(f"args: {k!r} is required by {d['engine']}")
    for k, v in d["env"].items():
        allowed = engine["env"].get(k)
        if allowed is None or not isinstance(v, str) or not allowed.fullmatch(v) or ".." in v:
            raise SpecError(f"env: {k!r} is not allowed or has a bad value")
    return Spec(**{k: d[k] for k in FIELDS})
