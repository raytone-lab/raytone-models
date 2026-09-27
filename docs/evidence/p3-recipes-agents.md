# P3: recipes and agents on the Jetson AGX Thor (2026-09-27)

| Component | State | Evidence |
|---|---|---|
| Recipe signing | **real data** | ed25519 key kept outside the repository; `packaging/allowed_signers` shipped to `/usr/share/raytone-models/allowed_signers`; on the Thor `raytone-models recipes --json`: `qwen38-27b-coder ready`, nothing refused |
| Recipe apply | **real data** | `raytone-models recipe apply qwen38-27b-coder` with the instance already running: the helper stopped the old unit, registered the recipe's spec on port 18001, started it; ready after 314 s (warm cache: torch.compile 1.2 s, weights 20 s, CUDA graphs about 2 min) against 15 min on a fresh cache |
| Recipe drafts | **code** | Laguna S 2.1 and Muse Glimmer 30B from Mia's parameters, unsigned until checked on the Thor |
| opencode | **real data** | P1: wrote and ran `hello.py`, output 55 |
| Claude Code 2.1.283 | **real data** | first run: vLLM's Anthropic endpoint refused `effort: high` ("Supported types are xhigh, medium, and low" from Qwen3.8's template); with `CLAUDE_CODE_EFFORT_LEVEL=medium` in the adapter: `claude -p "Create a file primes.py ..."` wrote and ran it, output `[2, 3, 5, 7, 11, 13, 17, 19, 23, 29]`, 38 s |
| Crush v0.96.1 | **real data** | `crush run "What is 12*12? ..."` → 144, 10 s |
| Pi 0.87.1 | **real data** | `pi -p --model raytone/qwen3.8-27b "What is 13*13? ..."` → 169, 3 s |
| Panel recipes section | **code** | not yet opened in a desktop session |
