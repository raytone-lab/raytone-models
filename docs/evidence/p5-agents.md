# P5: agents on local models, the Jetson AGX Thor (2026-09-28)

All through the router (127.0.0.1:8090) to Nemotron 3.5 Lightning on SGLang (the Raytone Studio recipe), after `raytone-models agent connect <agent>`:

| Agent | State | Evidence |
|---|---|---|
| OpenCode | **real data** | `opencode run "What is 12*12? ..."` → 144, 5.4 s (it waits for stdin: run it with `< /dev/null` when scripted) |
| Claude Code | **real data** | `claude -p "What is 13*13? ..."` → 169, through the Anthropic endpoint; it warns that `nemotron-3.5-lightning` is not in its model catalog and assumes a 200k window |
| Crush | **real data** | `crush run "What is 14*14? ..."` → 196 |
| Pi | **real data** | `pi -p --model raytone/nemotron-3.5-lightning "What is 15*15? ..."` → 225 |
| Codex 0.157.1 | **real data, answers only** | a custom provider on the Responses API, which SGLang serves and the router forwards (no CC Switch in between): `codex exec "What is 16*16? ..."` → 256. A task that runs commands fails inside Codex's own sandbox: `bwrap: Creating new namespace failed: Permission denied`. The L4T kernel sets `kernel.apparmor_restrict_unprivileged_userns=1` and Arch ships no AppArmor profiles, so no unprivileged user namespace can be made (`unshare -U true` fails the same way). The model itself called `exec_command` correctly |
| GitHub Copilot CLI 1.0.88 | **real data** | its BYOK variables, offline (`COPILOT_OFFLINE=true`), written to `~/.config/environment.d/60-raytone-copilot.conf` (read by the Omarchy session at login; sourced by hand for the test): `copilot -p "What is 18*18? ..."` → 324 in 4 s; `copilot -p "Create primes.py ... then run it" --allow-all-tools` wrote the file (+23 lines) and `python3 primes.py` prints `[2, 3, 5, 7, 11, 13, 17, 19, 23, 29]` |
| Grok CLI 1.0.41 | **no local endpoint found** | no custom endpoint setting in the installed package (only `XAI_API_KEY`) |
| Oh My Pi, Hermes, OpenClaw | **code** | not connected yet; their launchers install the agent on first run (Oh My Pi reads a YAML `models.yml`) |
