#!/usr/bin/env bash
# Clone the two self-hosted CTF suites we train and evaluate against.
#   xbow  : 104 web challenges, flag injected at build time (--build-arg flag=)
#   argus : 71 challenges, each with a gold solve.py we use for smoke tests
#
# They land under env/benchmarks/ which is gitignored: they are large and have
# their own upstreams, so we track a pinned commit here rather than vendoring.
set -euo pipefail
cd "$(dirname "$0")"
DEST="benchmarks"
mkdir -p "$DEST"

clone_or_update() {
  local url="$1" dir="$2" ref="${3:-}"
  if [ -d "$DEST/$dir/.git" ]; then
    echo "updating $dir"; git -C "$DEST/$dir" fetch --quiet --depth 1 origin "${ref:-HEAD}"
  else
    echo "cloning $dir"; git clone --depth 1 ${ref:+--branch "$ref"} "$url" "$DEST/$dir"
  fi
}

clone_or_update https://github.com/xbow-engineering/validation-benchmarks.git xbow
clone_or_update https://github.com/pensar-x/argus-validation-benchmarks.git   argus

echo
echo "done. discovered challenges:"
python3 challenge.py --list | sed 's/^/  /'
