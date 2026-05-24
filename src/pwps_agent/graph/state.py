from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from pwps_agent.config import Settings
from pwps_agent.core.state import PWPSState
from pwps_agent.workflows.auto_draft import AutoDraftDependencies


@dataclass
class GraphRuntimeContext:
    settings: Settings
    dependencies: AutoDraftDependencies
    supervisor_planner: Any | None = None
    max_tool_retries: int = 0
    query_timeout_seconds: float | None = None
    max_parallel_queries: int = 4
    checkpoint_enabled: bool = False
    interrupt_after_steps: int | None = None


class GraphState(TypedDict):
    pwps_state: PWPSState
    context: GraphRuntimeContext
