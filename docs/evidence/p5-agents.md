# P5: agents on local models, the Jetson AGX Thor (2026-09-28)

All through the router (127.0.0.1:8090) to Nemotron 3.5 Lightning on SGLang (the Raytone Studio recipe), after `raytone-models agent connect <agent>`:

| Agent | State | Evidence |
|---|---|---|
| OpenCode | **real data** | `opencode run "What is 12*12? ..."` → 144, 5.4 s (it waits for stdin: run it with `< /dev/null` when scripted) |
| Claude Code | **real data** | `claude -p "What is 13*13? ..."` → 169, through the Anthropic endpoint; it warns that `nemotron-3.5-lightning` is not in its model catalog and assumes a 200k window |
| Crush | **real data** | `crush run "What is 14*14? ..."` → 196 |
| Pi | **real data** | `pi -p --model raytone/nemotron-3.5-lightning "What is 15*15? ..."` → 225 |
| Codex 0.157.1 | **real data, answers only** | a custom provider on the Responses API, which SGLang serves and the router forwards (no CC Switch in between): `codex exec "What is 16*16? ..."` → 256. A task that runs commands fails inside Codex's own sandbox: `bwrap: Creating new namespace failed: Permission denied`. The L4T kernel sets `kernel.apparmor_restrict_unprivileged_userns=1` and Arch ships no AppArmor profiles, so no unprivileged user namespace can be made (`unshare -U true` fails the same way). The model itself called `exec_command` correctly |
| Oh My Pi, Hermes, OpenClaw, Grok, Copilot | **code** | not connected yet; their launchers install the agent on first run |
