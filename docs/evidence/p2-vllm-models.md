# P2: the other vLLM models on the Jetson AGX Thor (2026-09-28)

| Model | State | Evidence |
|---|---|---|
| Laguna S 2.1 NVFP4 + DFlash | **real data, no recipe** | `vllm/vllm-openai` v0.25.1 (Mia's image; torch 2.11.0+cu130, arch list includes sm_110). With Mia's settings (0.85 of memory, 262144 context) it failed: weights took 95.63 GiB, leaving 1.39 GiB for a KV cache that needs 19.2 GiB. With 0.9, a 65536 context and an FP8 KV cache it came up after 1251 s (first start), answered 17*23 (298 tokens, 38 tokens/s) and wrote a `fib(n)` (3665 tokens, 24 tokens/s), its reasoning in the answer text rather than a separate field; lowest available memory 6.1 GiB, hottest zone 63 C. Too tight to sign as it is |
| Qwen3.8 Flash Next NVFP4 | **not tried** | the checkpoint is 123.62 GiB on disk; vLLM v0.30.0's engram config offers only `cpu_offload` (pinned memory) and sharding for its PLE table, and Mia's single-Spark recipe needs her own mmap patch (AGPL) to fit 121.7 GiB. Needs a decision |
