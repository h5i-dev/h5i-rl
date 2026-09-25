#!/usr/bin/env bash
cd "$(dirname "$0")"
VLLM_API_KEY=dummy codex exec --profile local --skip-git-repo-check "$(cat .prompt.txt)" < /dev/null 2>&1
