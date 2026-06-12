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

    error: Optional[str] = None
    execution_smoke: Optional[ExecutionSmokeResult] = None

    run_at: datetime = Field(default_factory=datetime.now)
    run_config: dict = Field(default_factory=dict)
