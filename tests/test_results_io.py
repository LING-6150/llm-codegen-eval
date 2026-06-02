from pathlib import Path

from llm_codegen_eval.core.batch_runner import is_infra_error, load_results, save_results
from llm_codegen_eval.core.result import EvalResult


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
