# P2: Ollama on the Jetson AGX Thor (2026-09-28)

Ollama is the Thor edition's own system service (`raytone-thor-ollama` 0.34.4, 127.0.0.1:11434); Raytone Models uses it as it is.

| Component | State | Evidence |
|---|---|---|
| Engines page | **real data** | `raytone-models engines`: `ollama True 0.34.4` |
| Library, run, stop | **real data** | `raytone-models ollama models`: `qwen3:1.7b` (2.0B Q4_K_M); `ollama run` keeps it in memory (`keep_alive -1`), `instances` shows `ollama:qwen3:1.7b ollama 11434 ready chat 4096`; `stop ollama:qwen3:1.7b` unloads it |
| Router | **real data** | `/v1/models` lists `qwen3:1.7b` next to the recipe's Nemotron; chat through the router: 17*23 (1819 tokens with its reasoning, 95 tokens/s, first token 0.33 s), `fib(n)` (1611 tokens, 104 tokens/s); `/v1/messages` (Anthropic) answers |
| Ollama on the GPU after a boot | **real data, a Thor edition issue** | after the 00:35 reboot Ollama had found no GPU (`inference compute id=cpu`, `size_vram 0`): the unit only waits for the network, and the GPU was not up yet. `systemctl restart ollama` found `CUDA0 NVIDIA Thor (compute 11.0)` and the model went to the GPU (`size_vram` 6.2 GB). Fix belongs in `raytone-thor-ollama` (order the unit after the GPU) and needs a reboot to check |
| Upgrades | **found on the Thor** | `systemctl --user enable --now` leaves a running router on the old code: restart it after installing (`systemctl --user restart raytone-models-router`) |
