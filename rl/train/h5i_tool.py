"""h5i verbs as verl `BaseTool`s, so verl's ToolAgentLoop owns the parts that are
hard to get right per version: generation, tool-call parsing, multi-turn
tokenization and the response mask. We only supply tool execution.

One class, parameterized by `config.verb`; the tool config yaml lists it once per
verb (see h5i_tools.yaml). The OpenAI schema for each verb is reused from
`agent/tools.py` so the training tool surface and the standalone-rollout tool
surface never drift apart.

Per-rollout isolation (the thing that bit us before): h5i keeps ONE browser
session per XDG_STATE_HOME, and a GRPO group runs many rollouts of the same
challenge concurrently. verl creates a fresh tool instance_id per *call*, but
`agent_data.request_id` is stable across a rollout's turns and unique between
rollouts -- so we key the isolated h5i state dir on request_id. All turns of one
rollout thus share one h5i session; different rollouts never collide.

Scope is enforced by construction: `browser_open` always opens the challenge's
own base_url (from the dataset row), never a URL the policy supplies.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Make `agent.tools` importable whether loaded as a package module or by verl's
# importlib-by-name loader (which puts only train/ on the path).
_RL_ROOT = Path(__file__).resolve().parent.parent
if str(_RL_ROOT) not in sys.path:
    sys.path.insert(0, str(_RL_ROOT))

from verl.tools.base_tool import BaseTool                       # noqa: E402
from verl.tools.schemas import OpenAIFunctionToolSchema, ToolResponse  # noqa: E402

from agent.tools import TOOLS, run_tool, episode_h5i_env        # noqa: E402

# verb -> OpenAI schema, reused from the standalone agent (minus declare_flag,
# which the tool loop does not need: ending a turn without a tool call ends the
# episode, and the reward reads the captured trajectory).
_SCHEMA = {t["function"]["name"]: t for t in TOOLS if t["function"]["name"] != "declare_flag"}
# browser_open opens the in-scope target only; drop the model-supplied url.
_SCHEMA["browser_open"] = {
    "type": "function",
    "function": {
        "name": "browser_open",
        "description": "Open the target application in the h5i browser, capturing its traffic.",
        "parameters": {"type": "object", "properties": {}},
    },
}

# Where per-rollout h5i state dirs live (see env isolation note above).
_STATE_ROOT = Path(__import__("os").environ.get(
    "H5I_RL_STATE_ROOT", "/tmp/h5i-rl-sessions"))


class H5iTool(BaseTool):
    def __init__(self, config: dict, tool_schema: OpenAIFunctionToolSchema | None = None):
        self.verb = config["verb"]                 # set before super(): schema lookup needs it
        super().__init__(config, tool_schema)
        self._reg: dict[str, dict] = {}            # instance_id -> create_kwargs (carries base_url)

    def get_openai_tool_schema(self) -> OpenAIFunctionToolSchema:
        return OpenAIFunctionToolSchema.model_validate(_SCHEMA[self.verb])

    async def create(self, instance_id: str | None = None, create_kwargs: dict | None = None,
                     **kwargs) -> tuple[str, ToolResponse]:
        iid = instance_id or str(uuid.uuid4())
        self._reg[iid] = dict(create_kwargs or {})   # {base_url, ...} from the dataset row
        return iid, ToolResponse()

    async def execute(self, instance_id: str, parameters: dict,
                      **kwargs) -> tuple[ToolResponse, float, dict]:
        ck = self._reg.get(instance_id, {})
        base_url = ck.get("base_url")
        agent_data = kwargs.get("agent_data")
        # stable per-rollout id -> one isolated h5i session shared by all its turns.
        rollout_id = getattr(agent_data, "request_id", None) or instance_id
        state_dir = _STATE_ROOT / str(rollout_id)
        state_dir.mkdir(parents=True, exist_ok=True)
        env = episode_h5i_env(state_dir)

        params = dict(parameters or {})
        if self.verb == "browser_open":
            params["url"] = base_url                 # scope enforced by construction
        obs = run_tool(self.verb, params, cwd=state_dir, env=env)
        # step reward stays 0: the episode-level, capture-backed reward is computed
        # by h5i_reward.compute_score over the finished trajectory.
        return ToolResponse(text=obs), 0.0, {}

    async def release(self, instance_id: str, **kwargs) -> None:
        self._reg.pop(instance_id, None)
