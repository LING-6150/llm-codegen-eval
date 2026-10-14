from dataclasses import dataclass, field
from typing import Literal
from pydantic import BaseModel, Field
from ..core.case import EvalCase
from ..core.result import ExecutionSmokeResult

Status = Literal["passed", "failed", "checker_error", "not_run", "not_applicable"]


class BehaviorCase(EvalCase):
    behavior_id: str
    contract_version: str = "1"


class BehaviorCheck(BaseModel):
    check_id: str
    status: Status
    detail: str | None = None


class BehaviorResult(BaseModel):
    status: Status
    contract_version: str = "1"
    checks: list[BehaviorCheck] = Field(default_factory=list)
    detail: str | None = None
    duration_ms: int = 0


@dataclass
class BrowserOutcome:
    smoke: ExecutionSmokeResult
    behavior: BehaviorResult
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    blocked_requests: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)
    evidence_errors: list[str] = field(default_factory=list)
