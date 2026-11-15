"""单次运行的数据；会话、权限和客户端仍由 Agent 持有。"""
from dataclasses import dataclass, field
from typing import Literal

from verification import CheckResult


@dataclass(frozen=True)
class RunResult:
    text: str
    stop_reason: str
    verification: CheckResult | None = None


@dataclass
class RunState:
    run_id: str | None = None
    user_input: str = ""
    phase: Literal["idle", "preparing", "model", "tools", "verifying",
                   "stopped", "interrupted"] = "idle"
    steps_used: int = 0
    pending_calls: dict[str, dict] = field(default_factory=dict)
    tool_results: list[dict] = field(default_factory=list)
    verification_attempts: int = 0
    verification: CheckResult | None = None
    events: list[dict] = field(default_factory=list)
    result: RunResult | None = None
    next_action: str = 'prepare'
    response: dict | None = None
    candidate: str | None = None
    request_inflight: str | None = None
    call_records: dict[str, dict] = field(default_factory=dict)
    active_batch: list[str] = field(default_factory=list)
    requires_verifier: bool = False
    last_event_id: int = 0
    usage_history: list[dict] = field(default_factory=list)
    unknown_usage: list[dict] = field(default_factory=list)
    limit_tokens_used: int = 0
    limit_usage_incomplete: bool = False
    limit_started_at: float | None = None

