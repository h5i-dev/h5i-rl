"""The slice of h5i the policy is allowed to call, as OpenAI-style tool schemas,
plus a thin executor that runs the real h5i CLI and returns a bounded
observation string.

Design notes:
- We expose a compact-but-expressive verb set (the vault-ctf runs show the model
  mostly needs browser + recon + websec). Fewer tools = shorter schemas = more
  of the context budget left for reasoning and observations.
- Every observation is truncated: agent context on the 3090 box is 128k but a
  raw response body can blow that in one turn. `_clip` keeps episodes bounded.
- `declare_flag` is the terminal action. The loop stops when it is called; the
  reward function checks the claim against captured traffic.
- The executor pins h5i's cwd to the episode workspace so each rollout has its
  own capture session (see the reset TODO on the h5i rl-env branch).
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

MAX_OBS_CHARS = 6000

# h5i keeps ONE browser session per XDG_STATE_HOME, so without isolation every
# episode would inherit the previous episode's open session and captures (proven
# on this box: a stale websecdojo.com/vault session leaked into a fresh run).
# We give each episode its own XDG_STATE_HOME + XDG_RUNTIME_DIR, and symlink the
# user's already-installed plugins in so websec/recon still resolve. No h5i code
# change needed -- this is the "per-episode reset" the README flags, solved with
# env isolation.
_DEFAULT_STATE = Path(os.environ.get("H5I_DEFAULT_STATE",
                                     str(Path.home() / ".local" / "state" / "h5i")))


def episode_h5i_env(root: Path) -> dict:
    """Build an isolated h5i environment rooted at `root` (one per episode)."""
    state, run = root / "state", root / "run"
    (state / "h5i").mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    run.chmod(0o700)
    plugins = state / "h5i" / "plugins"
    src = _DEFAULT_STATE / "plugins"
    if src.exists() and not plugins.exists():
        plugins.symlink_to(src)          # share installed plugins read-only
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = str(state)
    env["XDG_RUNTIME_DIR"] = str(run)
    return env


def _clip(s: str, n: int = MAX_OBS_CHARS) -> str:
    return s if len(s) <= n else s[:n] + f"\n...[clipped {len(s) - n} chars]"


# Tool schemas handed to the policy. Kept flat and literal so they serialize the
# same way every episode (stable prompts help GRPO's advantage estimates).
TOOLS = [
    {"type": "function", "function": {
        "name": "browser_open",
        "description": "Open a URL in the h5i browser, capturing the traffic it generates.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "browser_snapshot",
        "description": "Return the current page as a model should read it (refs like @e3).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "recon",
        "description": "Inventory what the target exposes: 'extract' (from loaded pages/bundles), "
                       "'known' (robots/sitemap/security.txt), or 'crawl' (bounded walk).",
        "parameters": {"type": "object", "properties": {
            "mode": {"type": "string", "enum": ["extract", "known", "crawl"]},
            "max_requests": {"type": "integer", "default": 50}},
            "required": ["mode"]}}},
    {"type": "function", "function": {
        "name": "websec_requests",
        "description": "List the captured HTTP messages by id (JSON).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "websec_show",
        "description": "Show one captured request or response by id.",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "raw": {"type": "boolean", "default": False}},
            "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "websec_replay",
        "description": "Re-send a captured request with edits, e.g. sets=['query.id=456','header.User-Agent=Agent33'].",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"},
            "sets": {"type": "array", "items": {"type": "string"}}},
            "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "websec_diff",
        "description": "Compare two captured responses by id.",
        "parameters": {"type": "object", "properties": {
            "a": {"type": "string"}, "b": {"type": "string"}}, "required": ["a", "b"]}}},
    {"type": "function", "function": {
        "name": "declare_flag",
        "description": "Terminal action: declare the recovered flag. Only call once you have "
                       "seen it in a captured response body or header.",
        "parameters": {"type": "object", "properties": {
            "flag": {"type": "string"}}, "required": ["flag"]}}},
]

# name -> argv builder (list of h5i args). declare_flag is handled by the loop.
_ARGV = {
    "browser_open":     lambda a: ["browser", "open", a["url"], "--capture", "--script"],
    "browser_snapshot": lambda a: ["browser", "snapshot"],
    "recon":            lambda a: ["recon", a["mode"]] +
                                  (["--max-requests", str(a.get("max_requests", 50))]
                                   if a["mode"] == "crawl" else []),
    "websec_requests":  lambda a: ["websec", "requests"],
    "websec_show":      lambda a: ["websec", "show", a["id"]] + (["--raw"] if a.get("raw") else []),
    "websec_replay":    lambda a: ["websec", "replay", a["id"]] +
                                  sum((["--set", s] for s in a.get("sets", [])), []),
    "websec_diff":      lambda a: ["websec", "diff", a["a"], a["b"]],
}


def run_tool(name: str, args: dict, cwd: Path, env: dict | None = None,
             h5i: str = "h5i", timeout: int = 90) -> str:
    """Execute one h5i verb, return a bounded observation. Never raises: a tool
    error is an observation the policy must react to, not an episode crash.
    `env` should come from episode_h5i_env() so the session stays isolated."""
    if name not in _ARGV:
        return f"error: unknown tool {name!r}"
    argv = [h5i] + _ARGV[name](args)
    try:
        cp = subprocess.run(argv, cwd=cwd, env=env, timeout=timeout,
                            text=True, capture_output=True)
    except subprocess.TimeoutExpired:
        return f"error: `{shlex.join(argv)}` timed out after {timeout}s"
    out = cp.stdout or ""
    if cp.returncode != 0:
        out += f"\n[exit {cp.returncode}] {cp.stderr}"
    return _clip(out.strip())
