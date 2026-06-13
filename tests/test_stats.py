import pytest

from llm_codegen_eval.core.result import EvalResult, RepairSummary
from llm_codegen_eval.core.stats import (
    estimate_pass_at_k,
    pass_at_k,
    raw_run_spread_by_case,
    stability_by_case,
    structural_pass_at_k_estimate,
)


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


@pytest.mark.parametrize(
    ("n", "c", "k", "expected"),
    [
        (3, 0, 1, 0.0),
        (3, 3, 1, 1.0),
        (3, 2, 2, 1.0),
        (4, 2, 1, 0.5),
        (3, 1, 3, 1.0),
        (3, 1, 4, None),
        (0, 0, 1, None),
        (3, 1, 0, None),
    ],
)
def test_estimate_pass_at_k_edges(n, c, k, expected):
    actual = estimate_pass_at_k(n, c, k)

    if expected is None:
        assert actual is None
    else:
        assert actual == pytest.approx(expected)


def test_structural_pass_at_k_estimate_averages_per_case_not_pooled():
    results = [
        result("case_a", True, 1),
        result("case_a", False, 2),
        result("case_b", True, 1),
    ]

    estimate = structural_pass_at_k_estimate(results, 1)

    assert estimate["pass_rate"] == pytest.approx((0.5 + 1.0) / 2)
    assert estimate["estimated_cases"] == 2


def test_repair_success_does_not_affect_structural_pass_estimate():
    repaired = result("case_a", False, 1)
    repaired.repair_summary = RepairSummary(attempted=True, succeeded=True)
    results = [repaired, result("case_a", False, 2)]

    assert pass_at_k(results, 2)["pass_rate"] == 0.0
    assert structural_pass_at_k_estimate(results, 1)["pass_rate"] == 0.0


def test_raw_run_spread_uses_first_shot_total_tokens_not_repair_tokens():
    first = result("case_a", True, 1)
    first.total_tokens = 100
    first.run_config["token_summary"] = {"total": 100}
    first.repair_summary = RepairSummary(
        attempted=True,
        succeeded=True,
        token_summary={"total": 9999},
    )
    second = result("case_a", True, 2)
    second.total_tokens = 200
    second.run_config["token_summary"] = {"total": 200}

    spread = raw_run_spread_by_case([first, second])

    assert spread["case_a"]["total_tokens"]["mean"] == pytest.approx(150)
    assert spread["case_a"]["total_tokens"]["stdev"] == pytest.approx(70.710678, rel=1e-5)


def test_execution_judged_predicate_is_single_source():
    """Guard Phase 2 invariant: the judged definition lives in exactly one place."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "llm_codegen_eval"
    hits = sum(
        path.read_text().count('failure_type != "checker_error"')
        for path in src.rglob("*.py")
    )
    assert hits == 1, f'expected single judged definition, found {hits}'
