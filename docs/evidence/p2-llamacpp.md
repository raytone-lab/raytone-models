# P2: llama.cpp on the Jetson AGX Thor (2026-09-28)

| Component | State | Evidence |
|---|---|---|
| llama.cpp image | **real data** | `raytone-models-build-engine llamacpp`: b11221 built with CUDA 13.0.2 for sm_110 (CUDA 13.2 builds give garbage on sm_110, ggml-org/llama.cpp#27763), `llama-server` only, on the CUDA 13.0.2 runtime image with libgomp1; the build fails if any shared library is missing (the first run failed on `libgomp.so.1`) |
| llamacpp engine | **real data** | `llama-server -m /hf/hub/<snapshot>/<file>.gguf --alias NAME --metrics` under the same confinement as the other engines; `--list-devices` in the container: `CUDA0: NVIDIA Thor (125809 MiB)` |
| unsloth/Qwen3-0.6B-GGUF Q4_K_M | **real data** | started with the arguments the Models page sends (ctx 32768, all layers on the GPU, flash attention, jinja): ready in 3 s, next to the Studio recipe (Nemotron + H3); 17*23 → 391, iterative `fib(n)` correct, 185-190 tokens/s; `/metrics` `llamacpp:tokens_predicted_total 1859` |
| Models page Run for GGUF | **code** | picks the downloaded variant's file (a split model's first part) and the vision projector; unit tests; not clicked in a desktop session |
