import importlib
import sys

from llm_codegen_eval.core.failure_taxonomy import (
    classify_first_shot,
    classify_repair,
    classify_replay_artifact,
)
from llm_codegen_eval.core.result import EvalResult, ExecutionSmokeResult, RepairSummary


def make_result(passed: bool = True, score: int = 100) -> EvalResult:
    return EvalResult(
        case_id="case_a",
        passed=passed,
        score=score,
        required_passed=1 if passed else 0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        generated_code="<h1>Hello</h1>",
    )


def with_smoke(result: EvalResult, passed: bool, failure_type: str) -> EvalResult:
    result.execution_smoke = ExecutionSmokeResult(
        applicable=True,
        passed=passed,
        failure_type=failure_type,
        detail=failure_type,
    )
    return result


def test_classifies_passed_result():
    classification = classify_first_shot(make_result())

    assert classification.layer == "passed"
    assert classification.category == "passed"
    assert classification.counts_as_model_quality is True


def test_classifies_infra_error_as_retryable_not_model_quality():
    result = make_result(passed=False, score=0)
    result.error = "Workflow error: Remote host terminated the handshake"

    classification = classify_first_shot(result)

    assert classification.layer == "infra"
    assert classification.category == "network_or_provider"
    assert classification.retryable is True
    assert classification.counts_as_model_quality is False


def test_classifies_empty_stream_infra_subcategory():
    result = make_result(passed=False, score=0)
    result.error = "Workflow error: CodeGenAgent produced empty code stream"

    classification = classify_first_shot(result)

    assert classification.layer == "infra"
    assert classification.category == "empty_stream"


def test_classifies_non_infra_generation_error():
    result = make_result(passed=False, score=0)
    result.error = "Workflow error: parse guardrail rejected malformed output"

    classification = classify_first_shot(result)

    assert classification.layer == "generation"
    assert classification.category == "other_generation_error"
    assert classification.counts_as_model_quality is False


def test_classifies_suspicious_empty_generation():
    result = make_result(passed=False, score=0)
    result.generated_code = ""
    result.generation_duration_ms = 17

    classification = classify_first_shot(result)

    assert classification.layer == "generation"
    assert classification.category == "suspicious_empty_generation"


def test_classifies_structural_required_failure_without_low_score_category():
    result = make_result(passed=False, score=30)

    classification = classify_first_shot(result)

    assert classification.layer == "structural"
    assert classification.category == "required_check_failed"
    assert classification.category != "low_score"


def test_classifies_structural_forbidden_pattern_before_required_failure():
    result = make_result(passed=False, score=0)
    result.forbidden_found = ["eval\\s*\\("]

    classification = classify_first_shot(result)

    assert classification.layer == "structural"
    assert classification.category == "forbidden_pattern"


def test_classifies_execution_smoke_app_failure_when_structural_passed():
    result = with_smoke(make_result(passed=True), passed=False, failure_type="console_error")

    classification = classify_first_shot(result)

    assert result.passed is True
    assert classification.layer == "execution_smoke"
    assert classification.category == "console_error"
    assert classification.counts_as_model_quality is True


def test_classifies_missing_element_execution_smoke_failure():
    result = with_smoke(make_result(passed=True), passed=False, failure_type="missing_element")

    classification = classify_first_shot(result)

    assert classification.layer == "execution_smoke"
    assert classification.category == "missing_element"


def test_classifies_checker_error_not_model_quality():
    result = with_smoke(make_result(passed=True), passed=False, failure_type="checker_error")

    classification = classify_first_shot(result)

    assert classification.layer == "checker"
    assert classification.category == "checker_error"
    assert classification.counts_as_model_quality is False


def test_precedence_infra_beats_structural_failure():
    result = make_result(passed=False, score=0)
    result.error = "I/O error on POST request"
    result.forbidden_found = ["document.write"]

    classification = classify_first_shot(result)

    assert classification.layer == "infra"


def test_repair_classification_preserves_success_and_failure_reasons():
    assert classify_repair(RepairSummary(attempted=True, succeeded=True, reason="repair_succeeded")).category == "repair_succeeded"
    assert classify_repair(RepairSummary(attempted=True, succeeded=False, reason="repair_generation_error")).category == "repair_generation_error"
    assert classify_repair(RepairSummary(attempted=True, succeeded=False, reason="repaired_still_failing")).category == "repaired_still_failing"


def test_repair_classification_preserves_skip_reasons():
    reasons = [
        "execution_smoke_passed",
        "not_whitelisted",
        "execution_smoke_missing",
        "execution_smoke_not_applicable",
        "first_shot_error",
    ]

    for reason in reasons:
        classification = classify_repair(
            RepairSummary(attempted=False, succeeded=False, reason=reason)
        )
        assert classification.layer == "repair"
        assert classification.category == reason


def test_replay_truncated_artifact_classification():
    result = make_result()
    result.generated_code_truncated = True

    classification = classify_replay_artifact(result)

    assert classification.layer == "replay"
    assert classification.category == "truncated_artifact"
    assert classification.counts_as_model_quality is False


def test_failure_taxonomy_imports_no_live_modules():
    for module_name in [
        "llm_codegen_eval.core.failure_taxonomy",
        "llm_codegen_eval.core.batch_runner",
        "llm_codegen_eval.clients.java_client",
        "llm_codegen_eval.core.metrics",
        "llm_codegen_eval.core.runner",
        "llm_codegen_eval.core.preflight",
    ]:
        sys.modules.pop(module_name, None)

    importlib.import_module("llm_codegen_eval.core.failure_taxonomy")

    assert "llm_codegen_eval.core.batch_runner" not in sys.modules
    assert "llm_codegen_eval.clients.java_client" not in sys.modules
    assert "llm_codegen_eval.core.metrics" not in sys.modules
    assert "llm_codegen_eval.core.runner" not in sys.modules
    assert "llm_codegen_eval.core.preflight" not in sys.modules
