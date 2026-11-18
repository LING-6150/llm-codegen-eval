"""EvalResult: outcome of running an EvalCase."""

from typing import Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from .case import ElementCheck


class ExecutionSmokeResult(BaseModel):
    """Smoke-level runtime/build validation kept separate from structural score."""

    applicable: bool
    passed: bool
    failure_type: str = "not_applicable"
    detail: Optional[str] = None
    duration_ms: int = 0
    checked_selectors: list[str] = Field(default_factory=list)


BehaviorStatus = Literal["passed", "failed", "checker_error", "not_run", "not_applicable"]


class BehaviorCheck(BaseModel):
    check_id: str
    status: BehaviorStatus
    detail: Optional[str] = None


class BehaviorResult(BaseModel):
    status: BehaviorStatus
    contract_version: str = "1"
    checks: list[BehaviorCheck] = Field(default_factory=list)
    detail: Optional[str] = None
    duration_ms: int = 0


class RepairSummary(BaseModel):
    """One-shot repair result kept separate from first-shot scoring."""

    attempted: bool
    succeeded: bool
    trigger_failure_type: Optional[str] = None
    reason: Optional[str] = None
    repaired_structural_passed: Optional[bool] = None
    repaired_score: Optional[int] = None
    repaired_execution_smoke: Optional[ExecutionSmokeResult] = None
    token_summary: Optional[dict] = None
    error: Optional[str] = None


class EvalResult(BaseModel):
    case_id: str
    passed: bool
    score: int  # 0-100

    required_passed: int
    required_total: int
    required_failed: list[ElementCheck] = Field(default_factory=list)

    optional_passed: int
    optional_total: int

    forbidden_found: list[str] = Field(default_factory=list)

    generation_duration_ms: int = 0
    review_score: Optional[int] = None
    review_passed: Optional[bool] = None

    total_tokens: int = 0

    generated_code: str = ""
    generated_code_truncated: bool = False
    generated_artifact_path: Optional[str] = None

    error: Optional[str] = None
    execution_smoke: Optional[ExecutionSmokeResult] = None
    repair_summary: Optional[RepairSummary] = None
    behavior_result: Optional[BehaviorResult] = None
    browser_evidence: dict[str, str] = Field(default_factory=dict)
    browser_diagnostics: dict = Field(default_factory=dict)

    run_at: datetime = Field(default_factory=datetime.now)
    run_config: dict = Field(default_factory=dict)
