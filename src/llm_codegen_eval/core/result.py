"""EvalResult: outcome of running an EvalCase."""

from typing import Optional
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
    # None = legacy v1 prompt (included case selectors in failure detail).
    prompt_version: Optional[int] = None


class FinalArtifactResult(BaseModel):
    """Scores for the files left on disk after Review/Refine.

    Legacy EvalResult fields score the SSE stream text and stay unchanged.
    """

    available: bool
    error: Optional[str] = None
    files: list[str] = Field(default_factory=list)
    content_sha256: Optional[str] = None
    artifact_path: Optional[str] = None
    generated_code_gen_type: Optional[str] = None

    passed: bool = False
    score: int = 0
    required_passed: int = 0
    required_total: int = 0
    required_failed: list[ElementCheck] = Field(default_factory=list)
    forbidden_found: list[str] = Field(default_factory=list)
    execution_smoke: Optional[ExecutionSmokeResult] = None


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
    final_artifact: Optional[FinalArtifactResult] = None

    run_at: datetime = Field(default_factory=datetime.now)
    run_config: dict = Field(default_factory=dict)
