"""Failure classification helpers without live-run dependencies."""

from dataclasses import dataclass

from .result import EvalResult, RepairSummary


EXECUTION_SMOKE_APP_FAILURES = {
    "load_failure",
    "console_error",
    "missing_element",
}


@dataclass(frozen=True)
class FailureClassification:
    """Read-only diagnostic classification for a saved eval result."""

    layer: str
    category: str
    reason: str
    retryable: bool = False
    counts_as_model_quality: bool = False


def is_infra_error(result: EvalResult) -> bool:
    """Return true for transient provider/network errors worth rerunning."""
    if not result.error:
        return False

    error = result.error.lower()
    transient_markers = [
        "remote host terminated",
        "handshake",
        "tls",
        "i/o error",
        "timeout",
        "timed out",
        "429",
        "too many requests",
        "connection reset",
        "connection refused",
        "connection aborted",
        "temporarily unavailable",
        "produced empty code stream",
        "returned empty code stream",
        "empty response from java service",
    ]
    return any(marker in error for marker in transient_markers)


def classify_infra_category(result: EvalResult) -> str:
    """Classify an infra/provider error using the same markers as retry logic."""
    if not result.error:
        return "network_or_provider"
    error = result.error.lower()
    if "empty response from java service" in error:
        return "empty_response"
    if "produced empty code stream" in error or "returned empty code stream" in error:
        return "empty_stream"
    if "health" in error:
        return "health_gate"
    return "network_or_provider"


def is_suspicious_empty_generation(result: EvalResult) -> bool:
    """Detect near-zero-duration empty outputs with no explicit error."""
    return (
        not result.passed
        and result.score == 0
        and not result.error
        and result.generation_duration_ms < 1000
        and not result.generated_code.strip()
    )


def classify_first_shot(result: EvalResult) -> FailureClassification:
    """Classify the primary first-shot failure layer.

    Precedence:
    infra > generation > structural > checker > execution_smoke > passed.
    Repair and replay are intentionally classified by separate helpers.
    """
    if is_infra_error(result):
        return FailureClassification(
            layer="infra",
            category=classify_infra_category(result),
            reason=result.error or "infra/provider error",
            retryable=True,
            counts_as_model_quality=False,
        )

    if is_suspicious_empty_generation(result):
        return FailureClassification(
            layer="generation",
            category="suspicious_empty_generation",
            reason="empty code with near-zero generation duration",
            retryable=False,
            counts_as_model_quality=False,
        )

    if result.error:
        return FailureClassification(
            layer="generation",
            category="other_generation_error",
            reason=result.error,
            retryable=False,
            counts_as_model_quality=False,
        )

    if not result.passed:
        if result.forbidden_found:
            return FailureClassification(
                layer="structural",
                category="forbidden_pattern",
                reason=", ".join(result.forbidden_found),
                retryable=False,
                counts_as_model_quality=True,
            )
        return FailureClassification(
            layer="structural",
            category="required_check_failed",
            reason=f"{result.required_passed}/{result.required_total} required checks passed",
            retryable=False,
            counts_as_model_quality=True,
        )

    if (
        result.execution_smoke is not None
        and result.execution_smoke.applicable
        and result.execution_smoke.failure_type == "checker_error"
    ):
        return FailureClassification(
            layer="checker",
            category="checker_error",
            reason=result.execution_smoke.detail or "execution smoke checker error",
            retryable=False,
            counts_as_model_quality=False,
        )

    if (
        result.execution_smoke is not None
        and result.execution_smoke.applicable
        and not result.execution_smoke.passed
        and result.execution_smoke.failure_type in EXECUTION_SMOKE_APP_FAILURES
    ):
        return FailureClassification(
            layer="execution_smoke",
            category=result.execution_smoke.failure_type,
            reason=result.execution_smoke.detail or result.execution_smoke.failure_type,
            retryable=False,
            counts_as_model_quality=True,
        )

    return FailureClassification(
        layer="passed",
        category="passed",
        reason="first-shot structural evaluation passed",
        retryable=False,
        counts_as_model_quality=True,
    )


def classify_repair(summary: RepairSummary | None) -> FailureClassification:
    """Classify one-shot repair status without affecting first-shot metrics."""
    if summary is None:
        return FailureClassification(
            layer="repair",
            category="repair_not_attempted",
            reason="repair summary missing",
            retryable=False,
            counts_as_model_quality=False,
        )
    category = summary.reason or "repair_not_attempted"
    return FailureClassification(
        layer="repair",
        category=category,
        reason=category,
        retryable=False,
        counts_as_model_quality=False,
    )


def classify_replay_artifact(result: EvalResult) -> FailureClassification:
    """Classify replay-specific artifact availability."""
    if result.generated_code_truncated:
        return FailureClassification(
            layer="replay",
            category="truncated_artifact",
            reason="generated_code is truncated",
            retryable=False,
            counts_as_model_quality=False,
        )
    if not result.generated_code and not result.generated_artifact_path:
        return FailureClassification(
            layer="replay",
            category="missing_artifact",
            reason="no generated code or artifact sidecar is available",
            retryable=False,
            counts_as_model_quality=False,
        )
    return FailureClassification(
        layer="replay",
        category="available",
        reason="complete artifact data is available",
        retryable=False,
        counts_as_model_quality=False,
    )
