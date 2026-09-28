# Raytone Models

A local model manager for [Omarchy](https://github.com/basecamp/omarchy): pick an inference engine,
download models from Hugging Face, run them, point Omarchy's coding agents at them, generate
video, and apply Raytone AI Lab's recipes (models, engines and parameters checked together on a
given machine).

First target: the NVIDIA Jetson AGX Thor ([Omarchy Thor T5000](https://github.com/raytone-lab/Omarchy-Thor-T5000)).
What ran there, with its numbers, is in [`docs/evidence/`](docs/evidence). The app's pages were
rendered there offscreen (Video with fixture data, the others from the live backend); clicking
through them in a desktop session is still to do.

## What it has

- **The app** (`raytone-models-app`, one Quickshell window in Raytone's navy and gold, dark or
  light with the Omarchy theme): Recipes, Local models, Discover (search Hugging Face, pick a
  GGUF variant, with an estimate of whether it fits the memory), Running (memory, tokens/s), Chat,
  Video, Agents, Engines.
- **The CLI** (`raytone-models`): everything the app does; listings take `--json`, chat and video
  stream JSON lines. The app keeps no state of its own; it runs the CLI.
- **Engines**: vLLM, SGLang, llama.cpp and ComfyUI each run in a container as an unprivileged user
  with no capabilities, the model store read-only and the port on loopback only; their images are
  pinned by digest (or, when built on the device, by image ID) and never pulled at start. Ollama is
  the system's own service, used as it is:

  | Engine | Image | On the Thor |
  |---|---|---|
  | vLLM | `vllm/vllm-openai` v0.30.0 (and v0.25.1) | Qwen3.8 27B, Muse Glimmer 30B |
  | SGLang | NVIDIA's 26.05, or LMSYS's model images | Nemotron 3.5 Lightning (LMSYS image) |
  | llama.cpp | built on the device, CUDA 13.0 for sm_110 | GGUF (checked with Qwen3-0.6B Q4_K_M, 185-190 tokens/s) |
  | ComfyUI | built on the device on NVIDIA PyTorch 26.05 | MiniMax H3 text to video |
  | Ollama | the system's own service (its own library) | qwen3:1.7b, about 100 tokens/s |

- **A router** on `http://127.0.0.1:8090/v1`, OpenAI- and Anthropic-compatible (chat, completions,
  embeddings, messages, responses), that sends each request to the instance serving its model. The
  model name `local` is always the current model: the one started last (a model, a recipe, or
  `ollama run`), or the one chosen with `raytone-models use NAME` (Running's "Use for agents").
- **Agents** are connected once and never tied to a model: they get the router's address and the
  name `local`, so switching models needs no change to them. The context length is the engine's,
  set when the model starts; vLLM and SGLang refuse a longer request with an error the agent can act
  on (Ollama instead drops the start of it). OpenCode, Claude Code, Crush, Pi and Codex connect in one
  click (their own config files, restored byte for byte by Revert; in Pi, pick `raytone/local`
  with `/model`); GitHub Copilot CLI, which reads its
  endpoint from the environment only, starts on them with `raytone-models agent-exec copilot` (the
  Agents page's Launch). Gemini, Cursor and Muse Code cannot use a local endpoint, nor could Grok's
  CLI as installed; Oh My Pi, Hermes and OpenClaw are not connected yet.
- **Recipes**, signed by Raytone AI Lab (`ssh-keygen -Y`, verified offline):

  | Recipe | What | Checked on the Thor |
  |---|---|---|
  | `nemotron-35-lightning` | Nemotron 3.5 Lightning 30B-A3B NVFP4, DSpark, SGLang | about 130 tokens/s |
  | `raytone-studio` | Nemotron 3.5 Lightning + MiniMax H3 video | 480p 5 s video in 209 s while chat answers at 50-58 tokens/s |
  | `muse-glimmer-30b` | Muse Glimmer 30B NVFP4, DFlash, vLLM | about 32 tokens/s |
  | `qwen38-27b-coder` | Qwen3.8 27B NVFP4, MTP, 256K context, vLLM | 17-28 tokens/s on short prompts, 13 at a 170K prompt; needle recall to 170K |

  The language models' choices and parameters follow [Mia's AI Lab](https://mia-ai.net)'s single DGX
  Spark recipes, on engines that support the Thor's sm_110 (each recipe's `source` says what changed);
  MiniMax H3's files and graph follow Comfy-Org's text-to-video template.

## Install (Arch / Omarchy)

```
sudo pacman -S --needed python-huggingface-hub python-hf-xet    # hf, which downloads the models
cd packaging && makepkg -si
# once: the store's hub/ and xet/ belong to the user who downloads models
sudo install -d -o "$USER" -g "$USER" /var/lib/raytone-models/hf/hub /var/lib/raytone-models/hf/xet
systemctl --user enable --now raytone-models-router
# engines built on the device (each takes a while the first time)
raytone-models-build-engine comfyui
raytone-models-build-engine llamacpp
# the images the signed recipes pin (engines never pull at start: fetch them while online)
sudo docker pull vllm/vllm-openai@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90
sudo docker pull lmsysorg/sglang@sha256:a04d9a1a7ffe371b05230aecab001d4ba2bfa0e5c137bc56409ecc4cbc3ac864
# and a recipe's models
raytone-models recipe fetch raytone-studio
```

Models live in `/var/lib/raytone-models/hf`, a Hugging Face cache. Engines start through a small
privileged helper (polkit: local, active, wheel) that runs only what its checks accept. Over SSH,
where polkit does not let a remote session in, use `RAYTONE_MODELS_ELEVATE=sudo raytone-models ...`.

After an upgrade, restart the router: `systemctl --user restart raytone-models-router`.

Tests: `python3 -m unittest discover -s tests`. On a machine with Quickshell,
`tests/ui/render DATA_DIR SHOTS_DIR` renders every page offscreen (fixture data from `DATA_DIR`, or
the machine's own with `RAYTONE_UI_REAL=1`), and `tests/ui/probe` and `tests/ui/logic-probe` check the
backend and `logic.js` in Quickshell's own engine.

## Known limits on the Thor

- **768p video** needs the Thor edition's fan curve (raytone-thor-omarchy 0.1.0-11): with JetPack's the
  SoC peaked at 96 C, where the thermal guard (95 C) reboots; with it, 86 C (711 s for 5 s of video).
- **Codex** runs commands in its sandbox only with the Thor edition's user-namespace setting
  (raytone-thor-omarchy 0.1.0-11); the L4T kernel refuses unprivileged user namespaces otherwise.
- **Laguna S 2.1** (95.6 GiB of weights) failed with Mia's settings and started once on vLLM v0.25.1
  with 90% of memory, a 64K context and an FP8 KV cache (21 minutes the first time, 24-38 tokens/s),
  leaving about 6 GiB free, its reasoning in the answer text: an unsigned draft with those settings.
- **Qwen3.8 Flash Next** was tested with a vLLM image built on the Thor with Mia's AI Lab's AGPL patches
  (not part of this repository, never published) and a Thor-local recipe ([details](docs/evidence/p2-vllm-models.md)).
  **Ling 3.0 Flash** loads but writes stray tokens into code on sm_110.

## Models' own terms

Each model keeps its own licence: read its model card before you use it beyond a demo. The Video
page names MiniMax H3 as the model; the video files themselves carry no attribution.

MIT, © Raytone AI Lab and contributors.
