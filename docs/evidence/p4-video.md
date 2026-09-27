# P4: video with MiniMax H3 on the Jetson AGX Thor (2026-09-28)

| Component | State | Evidence |
|---|---|---|
| ComfyUI image | **real data** | `raytone-models-build-engine comfyui`: NGC PyTorch 26.05 (torch 2.12.0a0, CUDA 13.2, sm_110), ComfyUI v0.37.0, CPU torchaudio 2.11 (PyPI's aarch64 wheel is CUDA 13.0 and refuses CUDA 13.2); recorded in `/etc/raytone-models/engines.json` |
| ComfyUI engine | **real data** | `raytone-models start Comfy-Org/MiniMax-H3@bf92c409 --engine comfyui --name minimax-h3 --arg disable-smart-memory`: runs as the engine user with no capabilities, store read-only, port on loopback; `/system_stats` answers ComfyUI 0.37.0 |
| `raytone-models video` | **real data** | see the runs below; the video lands in `~/Videos/Raytone` |
| Video page | **real data, offscreen** | rendered on the Thor with the fixture backend; generating from the window in a desktop session is unchecked |
| Router | **code** | a ComfyUI instance is kept out of `/v1/models` and chat routing (unit test) |

Runs (prompt: a red fox trotting through snow in a birch forest at sunrise, with paws in snow, wind and birdsong; seed 42; 8-step turbo LoRA; H3 pruned int8, NVFP4 text encoder, fp16 video VAE):

| Size, length | Memory flag | Time | Lowest MemAvailable | Output |
|---|---|---|---|---|
| 480p (864x480), 5 s | `gpu-only`, Muse Glimmer 30B also running (51 GiB) | killed by the kernel OOM killer while loading the transformer | 0.2 GiB | none |
| 480p, 5 s | `gpu-only`, alone | 271 s (first step 58 s, then about 19 s per step) | 46.2 GiB | H.264 864x480 24 fps 5.17 s, AAC stereo 32 kHz, 0.95 MB |
| 480p, 5 s | `disable-smart-memory`, alone | 193 s | 92.6 GiB | as above |

| 768p (1344x768), 5 s | `disable-smart-memory`, alone | not finished: the SoC stayed at 85-89 C and reached 96 C, and the thermal guard (95 C) rebooted the Thor at 00:35 | — | none |

During the 480p runs the hottest zone peaked at 84 C (fan about 2300 rpm). The fan follows JetPack's stock "cool" profile, which scales with the margin to 115 C and was at about 2800 of 5371 rpm at 89 C. Until the fan curve or the guard is decided, the Video page offers 480p only.

With `gpu-only` ComfyUI keeps every model resident, so the text encoder (15 GB), the transformer (20 GB) and the VAE stay together; with `disable-smart-memory` each is freed after use, which on unified memory is also faster. The recipe uses `disable-smart-memory`.
