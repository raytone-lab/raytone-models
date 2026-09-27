# P2: SGLang on the Jetson AGX Thor (2026-09-28)

| Component | State | Evidence |
|---|---|---|
| SGLang engine | **real data** | `python3 -m sglang.launch_server` under the same confinement as vLLM (engine user, no capabilities, store read-only, port on loopback); `--enable-metrics` for the Running page |
| NGC `nvcr.io/nvidia/sglang:26.05-py3` | **real data, not usable for the recipes** | SGLang 0.5.11, torch 2.12.0a0 with sm_110, CUDA matmul on NVIDIA Thor (11, 0); no DSPARK, no `ling3` parsers; Nemotron 3.5 Lightning NVFP4 fails to load its MoE weights (`start (0) + length (1856) exceeds dimension size (928)`) |
| LMSYS `lmsysorg/sglang:dev-nemotron3-5-lightning` | **real data** | torch 2.13.0+cu130, arch list includes sm_110, DSPARK present |
| Nemotron 3.5 Lightning recipe | **real data** | DSpark draft (block 3), `mem-fraction-static` 0.6: weights 23.7 GB in 45 s, FlashInfer autotune, ready 8 minutes after a first start; 17*23 → `391` (272 tokens, 135 tokens/s), iterative `fib(n)` correct (605 tokens, 129 tokens/s, first token 0.10 s) |
| `USER`/`LOGNAME` | **real data** | the engine user has no passwd entry in the images; torch's compiler asks `getpass.getuser()` and failed until both are set |
| Ling 3.0 Flash | **real data, not usable** | LMSYS `dev-Ling-3.0-flash` (sm_110) with Mia's parameters: ready in 9 minutes, 17*23 → 391 and prose answers clean, but code answers carry stray tokens (`a + b八`, `a, b = 0, _List_to_string1`) in 2 of 4 runs with DSPARK, in every run without it, and still with a bf16 KV cache (`a + bノ`): a kernel problem on sm_110, not a setting. No recipe |
