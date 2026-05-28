from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase
from llm_codegen_eval.core.reporter import generate_ab_report
from llm_codegen_eval.core.result import EvalResult


def make_case(case_id: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        prompt="Create a page",
        code_type=CodeType.HTML,
        difficulty=Difficulty.EASY,
        required_checks=[],
    )


def make_result(case_id: str, passed: bool, score: int, run_index: int) -> EvalResult:
    return EvalResult(
        case_id=case_id,
        passed=passed,
        score=score,
        required_passed=1 if passed else 0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        generation_duration_ms=1000,
        run_config={"run_index": run_index, "runs_per_case": 2},
    )


def test_generate_ab_report_includes_summary_and_per_case_diff():
    cases = [make_case("case_a"), make_case("case_b")]
    results_a = [
        make_result("case_a", True, 90, 1),
        make_result("case_a", False, 60, 2),
        make_result("case_b", False, 40, 1),
        make_result("case_b", False, 50, 2),
    ]
    results_b = [
        make_result("case_a", True, 95, 1),
        make_result("case_a", True, 100, 2),
        make_result("case_b", True, 80, 1),
        make_result("case_b", False, 50, 2),
    ]

    report = generate_ab_report(results_a, results_b, cases, "agent_on", "agent_off")

    assert "# A/B Eval Report" in report
    assert "pass@2" in report
    assert "| case_a | html |" in report
    assert "| case_b | html |" in report
    assert "+50.0 pp" in report
