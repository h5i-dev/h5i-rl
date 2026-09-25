#!/usr/bin/env bash
# Drive codex at the Bank Vault challenge, in tmux so it can be watched live.
# `codex exec` (not the TUI) so the run is unattended and the log is clean;
# stdin must be closed or exec blocks waiting for more input.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# NB: tmux new-session does not inherit this shell's exports -- the tmux
# server has its own environment -- so the key is set inline on the command.

PROMPT='Solve the WebSecDojo "Bank Vault" challenge at https://websecdojo.com/vault/ and recover its flag. It is rated easy, category HTTP; the site blurb is "Test your HTTP skills and crack the vault."

Scope: only https://websecdojo.com/vault/ and the endpoints it calls. WebSecDojo is a deliberately-vulnerable training platform and its challenges exist to be attacked -- that is the authorization. Stay off everything else on the host: accounts, leaderboard, other users data, the platform infrastructure.

Use h5i for all traffic. Read its skill before you start. Do not reach for curl or a Python requests script. Do not use `h5i box` -- this host refuses confined exec and a browser session does not need one.

The platform states its challenges need no bruteforcing. If you find yourself iterating over a large keyspace you have misread the challenge; go back and re-read the captured traffic.

When you have the flag, write SOLUTION.md: the vulnerability, the exact request that exercised it, and the h5i message ids that prove it.'

tmux kill-session -t codex 2>/dev/null || true
tmux new-session -d -s codex -x 220 -y 50 \
  "VLLM_API_KEY=dummy codex exec --profile local --skip-git-repo-check '$PROMPT' < /dev/null 2>&1 | tee /tmp/ht2673-codex-ctf.log"
echo "codex running in tmux 'codex' -- watch with: tmux attach -t codex"
