"""Video generation with MiniMax H3 on a ComfyUI instance.

workflow() builds H3's text-to-video graph in ComfyUI's API format, following Comfy-Org's
template (video_minimax_h3_t2v): the pruned int8 transformer, the NVFP4 text encoder, the video
and audio VAEs, and by default the 8-step turbo LoRA. generate() queues it, polls the history
until it finishes, and fetches the video into the user's folder. Output is JSON lines, like chat.
"""
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

FILES = {
    "unet": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae": "minimax_h3_video_vae_fp16.safetensors",
    "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
    "lora": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
}
# 16:9 at H3's sizes, multiples of 32 (768p is the model's native short edge)
SIZES = {"480p": (864, 480), "768p": (1344, 768)}
OUT_DIR = pathlib.Path.home() / "Videos" / "Raytone"


class VideoError(RuntimeError):
    pass


def frames(seconds):
    """Frames at 24 fps, snapped up to the model's 17k+5 grid (5 s -> 124)."""
    n = max(5, round(seconds * 24))
    return n + (5 - n % 17) % 17


def workflow(prompt, *, size="480p", seconds=5, seed=0, turbo=True, files=FILES):
    if not isinstance(prompt, str) or not prompt.strip():
        raise VideoError("describe the video")
    if size not in SIZES:
        raise VideoError(f"size: one of {', '.join(SIZES)}")
    if not 1 <= seconds <= 15:
        raise VideoError("seconds: 1 to 15 (H3 is trained on about 5 to 15)")
    width, height = SIZES[size]
    model = ["2", 0] if turbo else ["1", 0]
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": files["unet"], "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": files["clip"], "type": "minimax", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": files["vae"]}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": files["audio_vae"]}},
        "6": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"clip": ["3", 0], "vae": ["4", 0], "prompt": prompt,
                                                                 "width": width, "height": height, "length": frames(seconds)}},
        "7": {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": ["6", 0]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "9": {"class_type": "BasicScheduler", "inputs": {"model": model, "scheduler": "simple", "steps": 8 if turbo else 20,
                                                          "denoise": 1.0}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["10", 0], "guider": ["7", 0], "sampler": ["8", 0],
                                                                  "sigmas": ["9", 0], "latent_image": ["6", 1]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}},
        "13": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["11", 0], "vae": ["5", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "audio": ["13", 0], "fps": 24}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": "video/MiniMax_H3",
                                                      "format": "auto", "codec": "auto"}},
    }
    if turbo:
        wf["2"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": files["lora"],
                                                                   "strength_model": 1.0}}
    return wf


def _call(base, path, body=None, timeout=30):
    req = urllib.request.Request(base.rstrip("/") + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _refusal(e):
    try:
        d = json.loads(e.read())
    except ValueError:
        return str(e)
    details = [f"{err.get('message')}: {err.get('details')}" for n in (d.get("node_errors") or {}).values()
               for err in n.get("errors", [])]
    return "; ".join(details) or (d.get("error") or {}).get("message") or str(e)


def cancel(base, pid):
    """Take a job off ComfyUI: out of the queue if it waits, interrupted if it runs."""
    for path, body in (("/queue", {"delete": [pid]}), ("/interrupt", {"prompt_id": pid})):
        try:
            _call(base, path, body, timeout=10)
        except (OSError, ValueError):
            pass


def generate(base, wf, out_dir=OUT_DIR, *, poll=1.0, timeout=3600, emit=print, stop=None):
    """stop() is asked between polls; when it answers true the job is cancelled on ComfyUI too."""
    t0 = time.time()
    try:
        pid = json.loads(_call(base, "/prompt", {"prompt": wf, "client_id": "raytone-models"}))["prompt_id"]
    except urllib.error.HTTPError as e:
        raise VideoError(f"ComfyUI refused the workflow: {_refusal(e)}") from None
    except (OSError, ValueError, KeyError) as e:
        raise VideoError(f"ComfyUI did not answer: {e}") from None
    emit({"state": "queued", "prompt_id": pid})
    while True:
        if stop and stop():
            cancel(base, pid)
            raise VideoError("stopped")
        if time.time() - t0 > timeout:
            cancel(base, pid)
            raise VideoError(f"no video after {timeout} s")
        try:
            h = json.loads(_call(base, f"/history/{urllib.parse.quote(pid)}")).get(pid)
        except (OSError, ValueError) as e:
            raise VideoError(f"ComfyUI did not answer: {e}") from None
        if h:
            break
        emit({"state": "running", "elapsed": round(time.time() - t0, 1)})
        time.sleep(poll)
    status = h.get("status") or {}
    if status.get("status_str") == "error":
        msg = next((m[1].get("exception_message") for m in status.get("messages", [])
                    if m and m[0] == "execution_error"), "generation failed")
        raise VideoError(str(msg).strip())
    files = [f for out in h.get("outputs", {}).values() for f in out.get("images", []) + out.get("videos", [])
             if isinstance(f, dict) and f.get("type") == "output"]
    if not files:
        raise VideoError("ComfyUI finished without a video")
    f = files[0]
    q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": "output"})
    try:
        data = _call(base, f"/view?{q}", timeout=120)
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / (time.strftime("%Y%m%d-%H%M%S-") + pathlib.Path(f["filename"]).name)
        path.write_bytes(data)
    except (OSError, ValueError) as e:
        raise VideoError(f"the video was made but could not be saved: {e}") from None
    emit({"done": str(path), "seconds": round(time.time() - t0, 1)})
    return path
