# Raytone Models

A local model manager for [Omarchy](https://github.com/basecamp/omarchy): pick an inference engine,
download models from Hugging Face, run them, point Omarchy's coding agents at them, generate
video, and apply Raytone AI Lab's recipes (models, engines and parameters checked together on a
given machine).

First target: the NVIDIA Jetson AGX Thor ([Omarchy Thor T5000](https://github.com/raytone-lab/Omarchy-Thor-T5000)).
Everything below was checked there; the evidence is in [`docs/evidence/`](docs/evidence).

## What it has

- **The app** (`raytone-models-app`, one Quickshell window in Raytone's navy and gold, dark or
  light with the Omarchy theme): Recipes, Local models, Discover (search Hugging Face, pick a
  GGUF variant that fits the memory), Running (memory, tokens/s), Chat, Video, Agents, Engines.
- **The CLI** (`raytone-models`): everything the app does, with `--json` output. The app keeps no
  state of its own; it runs the CLI.
- **Engines**, each in a container that runs as an unprivileged user with no capabilities, the
  model store read-only and its port on loopback only; images are pinned by digest (or, when built
  on the device, by image ID) and never pulled at start:

  | Engine | Image | On the Thor |
  |---|---|---|
  | vLLM | `vllm/vllm-openai` v0.30.0 (and v0.25.1) | Qwen3.8 27B, Muse Glimmer 30B |
  | SGLang | NVIDIA's 26.05, or LMSYS's model images | Nemotron 3.5 Lightning (LMSYS image) |
  | llama.cpp | built on the device, CUDA 13.0 for sm_110 | any GGUF from Discover |
  | ComfyUI | built on the device on NVIDIA PyTorch 26.05 | MiniMax H3 text to video |
  | Ollama | the system's own service (its own library) | qwen3:1.7b, about 100 tokens/s |

- **A router** on `http://127.0.0.1:8090/v1`, OpenAI- and Anthropic-compatible (chat, completions,
  embeddings, messages, responses), that sends each request to the instance serving its model.
- **Agents**: OpenCode, Claude Code, Crush, Pi and Codex connect to the local models in one click
  (their own config files, restored byte for byte by Revert); GitHub Copilot CLI, which reads its
  endpoint from the environment only, starts on them with `raytone-models agent-exec copilot` (the
  Agents page's Launch). Gemini, Cursor and Muse Code cannot use a local endpoint, nor could Grok's
  CLI as installed; Oh My Pi, Hermes and OpenClaw are not connected yet.
- **Recipes**, signed by Raytone AI Lab (`ssh-keygen -Y`, verified offline):

  | Recipe | What | Checked on the Thor |
  |---|---|---|
  | `nemotron-35-lightning` | Nemotron 3.5 Lightning 30B-A3B NVFP4, DSpark, SGLang | about 130 tokens/s |
  | `raytone-studio` | Nemotron 3.5 Lightning + MiniMax H3 video | 480p 5 s video in 209 s while chat answers at 50-58 tokens/s |
  | `muse-glimmer-30b` | Muse Glimmer 30B NVFP4, DFlash, vLLM | about 32 tokens/s |
  | `qwen38-27b-coder` | Qwen3.8 27B NVFP4, MTP, 256K context, vLLM | 17-28 tokens/s, needle recall to 170K |

  Model choices and parameters follow [Mia's AI Lab](https://mia-ai.net)'s single DGX Spark recipes,
  on engines that support the Thor's sm_110.

## Install (Arch / Omarchy)

```
cd packaging && makepkg -si
# once: the store's hub/ and xet/ belong to the user who downloads models
sudo install -d -o "$USER" -g "$USER" /var/lib/raytone-models/hf/hub /var/lib/raytone-models/hf/xet
systemctl --user enable --now raytone-models-router
# engines built on the device (each takes a while the first time)
raytone-models-build-engine comfyui
raytone-models-build-engine llamacpp
```

Models live in `/var/lib/raytone-models/hf`, a Hugging Face cache. Engines start through a small
privileged helper (polkit: local, active, wheel) that runs only what its checks accept. Over SSH,
where polkit does not let a remote session in, use `RAYTONE_MODELS_ELEVATE=sudo raytone-models ...`.

After an upgrade, restart the router: `systemctl --user restart raytone-models-router`.

Tests: `python3 -m unittest discover -s tests`. The app's pages render offscreen with
`tests/ui/render` (Quickshell).

## Known limits on the Thor

- **768p video** held the SoC near 89 C and peaked at 96 C, where the Thor edition's thermal guard
  (95 C) reboots; the app offers 480p only for now.
- **Codex** answers, but its own sandbox cannot run commands: the L4T kernel restricts unprivileged
  user namespaces through AppArmor and Arch ships no profiles.
- **Ollama** can start before the GPU after a boot and then stay on the CPU; `systemctl restart ollama`
  brings it to the GPU (the Thor edition's unit ordering, to be fixed there).
- **Laguna S 2.1** (95.6 GiB of weights) needs 90% of memory and a 64K context to start (21 minutes
  the first time, 24-38 tokens/s), leaving about 6 GiB free, and its reasoning arrives in the answer
  text: no recipe yet.
- **Qwen3.8 Flash Next** does not fit with upstream vLLM (its PLE table is pinned in memory next to
  a 123.6 GiB checkpoint). **Ling 3.0 Flash** loads but writes stray tokens into code on sm_110.

## Models' own terms

Models keep their licences: Muse Glimmer follows Meta's licence, Qwen models the Qwen licence, and
videos made with MiniMax H3 carry MiniMax H3's attribution (the Video page shows it).

MIT, © Raytone AI Lab and contributors.
