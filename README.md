# Raytone Models

A local model manager for [Omarchy](https://github.com/basecamp/omarchy): pick an inference engine
(vLLM, SGLang, llama.cpp, Ollama, ComfyUI for video), download models from Hugging Face, run
them, point Omarchy's coding agents at them, and apply Raytone AI Lab's recipes (models, engines
and parameters that are known to work together on a given machine).

First target: the NVIDIA Jetson AGX Thor ([Omarchy Thor T5000](https://github.com/raytone-lab/Omarchy-Thor-T5000)).

**Work in progress.** Tests: `python3 -m unittest discover -s . -p 'test_*.py'`.

MIT, © Raytone AI Lab and contributors.
