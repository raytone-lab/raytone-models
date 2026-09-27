# P1: first vertical slice on the Jetson AGX Thor (2026-09-27)

Every row is **real data** from the Thor (Omarchy 4.0.4 on the NVMe, L4T R39.2.1, 122 GiB unified memory)
unless marked otherwise.

| Component | State | Evidence |
|---|---|---|
| vLLM image | **real data** | `vllm/vllm-openai@sha256:8a69ffad…` (v0.30.0, arm64): torch 2.13.0+cu130, arch list includes `sm_110`, CUDA matmul on `NVIDIA Thor (11, 0)` |
| Package | **real data** | `raytone-models-0.1.0-1` built with makepkg on the Thor and installed; `raytone-engine` uid 955; `/var/cache/raytone-models` 0711, `/run/raytone-models/instances` 0755 root; helper root 0755 |
| Store | **real data** | moved to `/var/lib/raytone-models/hf` (root 0755; `hub/`, `xet/` the user's); `hf download` works against it; `raytone-models models` lists Qwen3.8 27B NVFP4 22.1 GiB complete |
| Managed start | **real data** | `raytone-models start RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead --engine vllm --name qwen3.8-27b` (MTP 3, 262144 ctx, 0.6 memory) → helper → `raytone-engine@qwen3-8-27b.service` → container `user=955:955 caps=[ALL] secopt=[no-new-privileges] groups=[983 987]` |
| Engine start time | **real data** | 15 min on a fresh cache (torch.compile, CUDA graphs); KV cache 1,269,714 tokens |
| Router | **real data** | user service `raytone-models-router` active; `/v1/models` lists `qwen3.8-27b` |
| opencode | **real data** | `raytone-models agent connect opencode`: provider `raytone` → `http://127.0.0.1:8090/v1`, model `raytone/qwen3.8-27b`, existing keys kept. `opencode run "Create a file hello.py that prints the 10th Fibonacci number, then run it..."` (opencode 1.18.32): wrote `hello.py`, ran it, output `55`, rc 0, 476 s (a long-context benchmark ran at the same time) |
| Panel | **code** | QML lints (two warnings the RaytoneOS panel also has), `omarchy-plugin-validate` passes; not yet opened in a desktop session |
| Agents other than opencode | **code** (catalog only) | P5 |

Speed, Qwen3.8 27B NVFP4 on vLLM 0.30 (no tuning yet; recipe parameters come from Mia's single-Spark recipes):

| Setting | First token | Decode |
|---|---|---|
| no speculative decoding, 31-token prompt | 0.29 s | 11.0–11.3 tok/s |
| MTP 3, through the router | 0.30–0.45 s | 28.3 tok/s (code), 17.6 tok/s (prose) |

Long context through the router (MTP 3, needle in the middle, 200 tokens out):

| Prompt | TTFT | Prefill | Decode | Recall |
|---|---|---|---|---|
| 6,827 | 3.9 s | 1,757 tok/s | 19.4 tok/s | OK |
| 27,106 | 15.4 s | 1,757 tok/s | 17.0 tok/s | OK |
| 54,295 | 43.3 s | 1,254 tok/s | 17.7 tok/s | OK |
| 108,744 | 138.7 s | 784 tok/s | 9.1 tok/s (opencode ran at the same time) | OK |
| 170,431 | 308.2 s | 553 tok/s | 13.0 tok/s | OK |

Security review (Codex): NO-GO on the first pass (3 P1: root container with a writable host cache;
store path swappable between check and mount; refused requests kept the connection open, so a smuggled
request passed the Host check; 3 P2: headers, timeouts, env by prefix). All fixed; second pass GO.
