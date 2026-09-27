# P6: the app and Hugging Face discovery on the Jetson AGX Thor (2026-09-27)

| Component | State | Evidence |
|---|---|---|
| `hub search` / `hub files` | **real data** | on the Thor against huggingface.co: `hub search Qwen3-0.6B-GGUF`, `hub files unsloth/Qwen3-0.6B-GGUF` listed the GGUF variants with sizes |
| `download --variant` | **real data** | `download unsloth/Qwen3-0.6B-GGUF --variant Q4_K_M`: `downloads --json` state `done`, 0.37 GiB / 0.37 GiB; `models --json` carries that download, so the app shows the model ready although the revision's full manifest is not downloaded |
| `chat` | **real data** | through the router to `qwen3.8-27b`: "What is 17*23?" → `391`, first token 0.41 s, 0.74 s total, usage 27 + 4 tokens |
| `stats` | **real data** | memory from `/proc/meminfo`: 80.7 / 123 GiB; vLLM counters from its `/metrics` (0 tokens/s while idle) |
| App pages, real backend | **real data, offscreen** | `RAYTONE_UI_REAL=1 tests/ui/render` on the Thor (Quickshell 0.3.1, software backend): all 7 pages in dark and light show the store's 12 models (drafts marked, Run disabled), the running instance on port 18001, the 4 connected agents, the pinned vLLM image |
| App in a desktop session | **code** | not yet opened in a logged-in Omarchy session: clicks, focus, the toast and `omarchy-launch-tui` are unchecked |
| Delete, cancel, HF token | **code** | unit tests only |

Found while checking with real data and fixed:
- a variant download read as "incomplete 3%" against the full manifest;
- partial blobs left by an interrupted earlier `hf download` (8 files, about 52 GB) made a complete Flash-Next read as "downloading"; the orphaned files were removed from the store.
