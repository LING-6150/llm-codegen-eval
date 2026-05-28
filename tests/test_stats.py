import pytest

from llm_codegen_eval.core.result import EvalResult
from llm_codegen_eval.core.stats import pass_at_k, stability_by_case


def result(case_id: str, passed: bool, run_index: int) -> EvalResult:
    return EvalResult(
        case_id=case_id,
        passed=passed,
        score=100 if passed else 50,
        required_passed=1 if passed else 0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        run_config={"run_index": run_index, "runs_per_case": 3},
    )


def test_pass_at_k_counts_cases_with_any_success_in_first_k_runs():
    results = [
        result("case_a", False, 1),
        result("case_a", True, 2),
        result("case_a", False, 3),
        result("case_b", False, 1),
        result("case_b", False, 2),
        result("case_b", True, 3),
        result("case_c", False, 1),
        result("case_c", False, 2),
        result("case_c", False, 3),
    ]

    assert pass_at_k(results, 1)["pass_rate"] == pytest.approx(0)
    assert pass_at_k(results, 2)["pass_rate"] == pytest.approx(1 / 3)
    assert pass_at_k(results, 3)["pass_rate"] == pytest.approx(2 / 3)


def test_stability_by_case_reports_pass_count_over_total_runs():
    results = [
        result("case_a", False, 1),
        result("case_a", True, 2),
        result("case_a", True, 3),
    ]

    stability = stability_by_case(results)

    assert stability["case_a"]["passed"] == 2
    assert stability["case_a"]["total"] == 3
    assert stability["case_a"]["label"] == "2/3"
    assert stability["case_a"]["stable"] is False
