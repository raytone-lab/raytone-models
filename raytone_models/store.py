"""The model store: a Hugging Face cache (HF_HOME/hub), the layout huggingface_hub and the engines share.

Each model is models--ORG--NAME with content-addressed files in blobs/ and one directory per
downloaded commit in snapshots/COMMIT, whose files are links into blobs/. A download in
progress leaves *.incomplete blobs.
"""
import dataclasses
import json
import os
import pathlib

DEFAULT_HOME = pathlib.Path(os.environ.get("XDG_DATA_HOME", pathlib.Path.home() / ".local/share")) / "raytone/hf"


@dataclasses.dataclass(frozen=True)
class Model:
    repo: str
    revision: str
    snapshot: str          # relative to hub/, what an instance spec names
    format: str            # safetensors | gguf | diffusion | unknown
    quant: str             # NVFP4, FP8, int4 ... or ""
    size: int              # bytes, each blob once
    files: list
    incomplete: int        # blobs still downloading
    missing: list          # links whose blob is gone

    def to_dict(self):
        return dataclasses.asdict(self)


def home():
    return pathlib.Path(os.environ.get("RAYTONE_MODELS_HOME", DEFAULT_HOME))


def _read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _quant(snap):
    q = _read_json(snap / "config.json").get("quantization_config") or {}
    algo = q.get("quant_algo") or q.get("format") or q.get("quant_method") or ""
    if not algo:
        hq = _read_json(snap / "hf_quant_config.json").get("quantization") or {}
        algo = hq.get("quant_algo") or ""
    return str(algo)


def _format(files):
    if any(f.endswith(".gguf") for f in files):
        return "gguf"
    if any(f.startswith(("diffusion_models/", "transformer/")) for f in files):
        return "diffusion"
    if any(f.endswith(".safetensors") for f in files):
        return "safetensors"
    return "unknown"


def list_models(hf_home=None):
    hub = pathlib.Path(hf_home or home()) / "hub"
    out = []
    if not hub.is_dir():
        return out
    for root in sorted(hub.glob("models--*--*")):
        repo = root.name[len("models--"):].replace("--", "/", 1)
        incomplete = sum(1 for _ in (root / "blobs").glob("*.incomplete")) if (root / "blobs").is_dir() else 0
        for snap in sorted((root / "snapshots").glob("*")) if (root / "snapshots").is_dir() else []:
            files, missing, blobs = [], [], set()
            for p in sorted(snap.rglob("*")):
                if p.is_dir() and not p.is_symlink():
                    continue
                rel = p.relative_to(snap).as_posix()
                target = p.resolve()
                if not target.is_file():
                    missing.append(rel)
                    continue
                files.append(rel)
                blobs.add(target)
            out.append(Model(repo=repo, revision=snap.name, snapshot=f"{root.name}/snapshots/{snap.name}",
                             format=_format(files), quant=_quant(snap), size=sum(b.stat().st_size for b in blobs),
                             files=files, incomplete=incomplete, missing=missing))
    return out
