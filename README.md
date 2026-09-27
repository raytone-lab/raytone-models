# Raytone Models

A local model manager for [Omarchy](https://github.com/basecamp/omarchy): pick an inference engine
(vLLM, SGLang, llama.cpp, Ollama, ComfyUI for video), download models from Hugging Face, run
them, point Omarchy's coding agents at them, and apply Raytone AI Lab's recipes (models, engines
and parameters that are known to work together on a given machine).

First target: the NVIDIA Jetson AGX Thor ([Omarchy Thor T5000](https://github.com/raytone-lab/Omarchy-Thor-T5000)).

**Work in progress.** Tests: `python3 -m unittest discover -s . -p 'test_*.py'`.

## Install (Arch / Omarchy)

```
cd packaging && makepkg -si
# once: the store's hub/ and xet/ belong to the user who downloads models
sudo install -d -o "$USER" -g "$USER" /var/lib/raytone-models/hf/hub /var/lib/raytone-models/hf/xet
systemctl --user enable --now raytone-models-router
```

Models live in `/var/lib/raytone-models/hf` (a Hugging Face cache; `HF_HOME=/var/lib/raytone-models/hf hf download ...`
fills it). Engines run through the privileged helper as the `raytone-engine` user; the router answers on
`http://127.0.0.1:8090/v1`. Over SSH, where polkit does not let a remote session in, use
`RAYTONE_MODELS_ELEVATE=sudo raytone-models ...`.

MIT, © Raytone AI Lab and contributors.
