# P5: agents on local models, the Jetson AGX Thor (2026-09-28)

All through the router (127.0.0.1:8090) to Nemotron 3.5 Lightning on SGLang (the Raytone Studio recipe), after `raytone-models agent connect <agent>`:

| Agent | State | Evidence |
|---|---|---|
| OpenCode | **real data** | `opencode run "What is 12*12? ..."` → 144, 5.4 s (it waits for stdin: run it with `< /dev/null` when scripted) |
| Claude Code | **real data** | `claude -p "What is 13*13? ..."` → 169, through the Anthropic endpoint; it warns that `nemotron-3.5-lightning` is not in its model catalog and assumes a 200k window |
| Crush | **real data** | `crush run "What is 14*14? ..."` → 196 |
| Pi | **real data** | `pi -p --model raytone/nemotron-3.5-lightning "What is 15*15? ..."` → 225 |
| Codex 0.157.1 | **real data** | a custom provider on the Responses API, which SGLang serves and the router forwards (no CC Switch): `codex exec "What is 16*16? ..."` → 256. Commands first failed in Codex's own sandbox (`bwrap: Creating new namespace failed`: the L4T kernel's `kernel.apparmor_restrict_unprivileged_userns=1`, no AppArmor profiles on Arch); with the Thor edition's sysctl set to 0 (raytone-thor-omarchy 0.1.0-11), `codex exec --sandbox workspace-write "Create primes.py ... then run it"` wrote the file and ran it: `[2, 3, 5, 7, 11, 13, 17, 19, 23, 29]` |
| GitHub Copilot CLI 1.0.88 | **real data** | its BYOK variables, offline (`COPILOT_OFFLINE=true`), in `~/.config/raytone-models/agents/copilot.env` (0600), which reach Copilot only when it is started with `raytone-models agent-exec copilot` (the Agents page's Launch does): `agent-exec copilot -p "What is 19*19? ..."` → 361; with the same variables, `copilot -p "Create primes.py ... then run it" --allow-all-tools` wrote the file and `python3 primes.py` prints `[2, 3, 5, 7, 11, 13, 17, 19, 23, 29]` |
| Grok CLI 1.0.41 | **no local endpoint found** | no custom endpoint setting in the installed package (only `XAI_API_KEY`) |
| Oh My Pi, Hermes, OpenClaw | **code** | not connected yet; their launchers install the agent on first run (Oh My Pi reads a YAML `models.yml`) |
