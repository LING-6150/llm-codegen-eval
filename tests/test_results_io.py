from pathlib import Path
import json

from llm_codegen_eval.core.batch_runner import is_infra_error, load_results, save_results
from llm_codegen_eval.core.result import EvalResult, ExecutionSmokeResult, RepairSummary


def test_save_and_load_results_round_trip(tmp_path: Path):
    path = tmp_path / "raw.json"
    results = [
        EvalResult(
            case_id="case_a",
            passed=True,
            score=100,
            required_passed=1,
            required_total=1,
            optional_passed=0,
            optional_total=0,
            run_config={"run_index": 1},
        )
    ]

    save_results(results, path)
    loaded = load_results(path)

    assert len(loaded) == 1
    assert loaded[0].case_id == "case_a"
    assert loaded[0].passed is True
    assert loaded[0].run_config["run_index"] == 1


def test_save_and_load_results_round_trip_execution_smoke(tmp_path: Path):
    path = tmp_path / "raw.json"
    results = [
        EvalResult(
            case_id="case_a",
            passed=True,
            score=100,
            required_passed=1,
            required_total=1,
            optional_passed=0,
            optional_total=0,
            execution_smoke=ExecutionSmokeResult(
                applicable=True,
                passed=False,
                failure_type="console_error",
                detail="boom",
                checked_selectors=["h1"],
            ),
        )
    ]

    save_results(results, path)
    loaded = load_results(path)

    assert loaded[0].execution_smoke is not None
    assert loaded[0].execution_smoke.failure_type == "console_error"
    assert loaded[0].execution_smoke.checked_selectors == ["h1"]


def test_load_results_accepts_legacy_raw_without_execution_smoke(tmp_path: Path):
    path = tmp_path / "legacy_raw.json"
    path.write_text(
        json.dumps([
            {
                "case_id": "case_a",
                "passed": True,
                "score": 100,
                "required_passed": 1,
                "required_total": 1,
                "required_failed": [],
                "optional_passed": 0,
                "optional_total": 0,
                "forbidden_found": [],
                "generation_duration_ms": 10,
                "review_score": None,
                "review_passed": None,
                "total_tokens": 0,
                "generated_code": "<h1>Hello</h1>",
                "error": None,
                "run_at": "2026-06-11T00:00:00",
                "run_config": {"run_index": 1},
            }
        ]),
        encoding="utf-8",
    )

    loaded = load_results(path)

    assert len(loaded) == 1
    assert loaded[0].passed is True
    assert loaded[0].execution_smoke is None
    assert loaded[0].repair_summary is None


def test_save_and_load_results_round_trip_repair_summary(tmp_path: Path):
    path = tmp_path / "raw.json"
    results = [
        EvalResult(
            case_id="case_a",
            passed=True,
            score=100,
            required_passed=1,
            required_total=1,
            optional_passed=0,
            optional_total=0,
            repair_summary=RepairSummary(
                attempted=True,
                succeeded=True,
                trigger_failure_type="console_error",
                reason="repair_succeeded",
                repaired_structural_passed=True,
                repaired_score=100,
                repaired_execution_smoke=ExecutionSmokeResult(
                    applicable=True,
                    passed=True,
                    failure_type="none",
                ),
                token_summary={"total": 42},
            ),
        )
    ]

    save_results(results, path)
    loaded = load_results(path)

    assert loaded[0].repair_summary is not None
    assert loaded[0].repair_summary.succeeded is True
    assert loaded[0].repair_summary.token_summary == {"total": 42}


def test_is_infra_error_detects_transient_provider_failures():
    result = EvalResult(
        case_id="case_a",
        passed=False,
        score=0,
        required_passed=0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        error='Workflow error: I/O error on POST request: Remote host terminated the handshake',
    )

    assert is_infra_error(result) is True


def test_is_infra_error_detects_empty_stream_workflow_guardrail():
    result = EvalResult(
        case_id="case_a",
        passed=False,
        score=0,
        required_passed=0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        error="Workflow error: java.lang.IllegalStateException: CodeGenAgent produced empty code stream",
    )

    assert is_infra_error(result) is True


def test_is_infra_error_detects_empty_java_service_response():
    result = EvalResult(
        case_id="case_a",
        passed=False,
        score=0,
        required_passed=0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        error="Infra error: empty response from Java service",
    )

    assert is_infra_error(result) is True


def test_is_infra_error_does_not_retry_empty_parse_guardrail():
    result = EvalResult(
        case_id="case_a",
        passed=False,
        score=0,
        required_passed=0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        error="Workflow error: java.lang.IllegalStateException: Parsed multi-file code is empty",
    )

    assert is_infra_error(result) is False


def test_is_infra_error_ignores_eval_failures():
    result = EvalResult(
        case_id="case_a",
        passed=False,
        score=50,
        required_passed=0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        error=None,
    )

    assert is_infra_error(result) is False
