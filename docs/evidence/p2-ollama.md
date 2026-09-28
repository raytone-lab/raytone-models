# P2: Ollama on the Jetson AGX Thor (2026-09-28)

Ollama is the Thor edition's own system service (`raytone-thor-ollama` 0.34.4, 127.0.0.1:11434); Raytone Models uses it as it is.

| Component | State | Evidence |
|---|---|---|
| Engines page | **real data** | `raytone-models engines`: `ollama True 0.34.4` |
| Library, run, stop | **real data** | `raytone-models ollama models`: `qwen3:1.7b` (2.0B Q4_K_M); `ollama run` keeps it in memory (`keep_alive -1`), `instances` shows `ollama:qwen3:1.7b ollama 11434 ready chat 4096`; `stop ollama:qwen3:1.7b` unloads it |
| Router | **real data** | `/v1/models` lists `qwen3:1.7b` next to the recipe's Nemotron; chat through the router: 17*23 (1819 tokens with its reasoning, 95 tokens/s, first token 0.33 s), `fib(n)` (1611 tokens, 104 tokens/s); `/v1/messages` (Anthropic) answers |
| Ollama on the GPU after a boot | **real data** | after the 00:35 reboot Ollama had found no GPU (`inference compute id=cpu`): it started at 13.6 s, before `nv-load-display-modules` loaded the NVIDIA module at 15.1 s. With raytone-thor-ollama 0.34.4-4 (ordered after that unit) and a reboot: the module finished at 16.54 s, Ollama started at 16.54 s and found `CUDA0` (compute 11.0) at 18.97 s |
| Upgrades | **found on the Thor** | `systemctl --user enable --now` leaves a running router on the old code: restart it after installing (`systemctl --user restart raytone-models-router`) |
