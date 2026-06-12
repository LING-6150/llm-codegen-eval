from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase
from llm_codegen_eval.core.reporter import generate_ab_report, generate_markdown
from llm_codegen_eval.core.result import EvalResult, ExecutionSmokeResult, RepairSummary


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


def make_error_result(case_id: str, error: str, run_index: int = 1) -> EvalResult:
    result = make_result(case_id, False, 0, run_index)
    result.error = error
    return result


def make_suspicious_result(case_id: str, run_index: int = 1) -> EvalResult:
    result = make_result(case_id, False, 0, run_index)
    result.generation_duration_ms = 17
    result.generated_code = ""
    result.error = None
    return result


def make_retry_result(case_id: str, retries_used: int) -> EvalResult:
    result = make_result(case_id, True, 90, 1)
    result.run_config["infra_retries_used"] = retries_used
    return result


def with_execution(
    result: EvalResult,
    passed: bool,
    failure_type: str = "none",
    detail: str | None = None,
) -> EvalResult:
    result.execution_smoke = ExecutionSmokeResult(
        applicable=True,
        passed=passed,
        failure_type=failure_type,
        detail=detail,
        checked_selectors=["h1"],
    )
    return result


def with_repair(
    result: EvalResult,
    succeeded: bool,
    token_total: int = 0,
    reason: str | None = None,
) -> EvalResult:
    result.repair_summary = RepairSummary(
        attempted=True,
        succeeded=succeeded,
        trigger_failure_type="console_error",
        reason=reason or ("repair_succeeded" if succeeded else "repaired_still_failing"),
        repaired_structural_passed=succeeded,
        repaired_score=100 if succeeded else 0,
        repaired_execution_smoke=ExecutionSmokeResult(
            applicable=True,
            passed=succeeded,
            failure_type="none" if succeeded else "console_error",
        ),
        token_summary={"total": token_total} if token_total else None,
    )
    return result


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
    assert "## Winner Summary" in report
    assert "## Improvements" in report
    assert "## Regressions" in report
    assert "## Unstable Cases" in report
    assert "pass@2" in report
    assert "| Infra retries used | 0 | 0 | +0 |" in report
    assert "| case_a | html |" in report
    assert "| case_b | html |" in report
    assert "+50.0 pp" in report
    assert "`case_b`: A failed, B passed" in report


def test_generate_ab_report_includes_token_usage_when_provided():
    cases = [make_case("case_a")]
    results_a = [make_result("case_a", True, 90, 1)]
    results_b = [make_result("case_a", True, 90, 1)]

    report = generate_ab_report(
        results_a,
        results_b,
        cases,
        "pruning_off",
        "pruning_on",
        token_summary_a={
            "input": 1000,
            "output": 200,
            "total": 1200,
            "by_agent": {"CodeGenAgent": {"input": 1000, "output": 200, "total": 1200}},
        },
        token_summary_b={
            "input": 700,
            "output": 180,
            "total": 880,
            "by_agent": {"CodeGenAgent": {"input": 700, "output": 180, "total": 880}},
        },
    )

    assert "## Token Usage" in report
    assert "| Total tokens | 1,200 | 880 | -320 (-26.7%) |" in report
    assert "| CodeGenAgent | 1,200 | 880 | -320 (-26.7%) |" in report


def test_generate_ab_report_sums_infra_retries_used():
    cases = [make_case("case_a"), make_case("case_b")]
    results_a = [make_retry_result("case_a", 0), make_retry_result("case_b", 1)]
    results_b = [make_retry_result("case_a", 2), make_retry_result("case_b", 1)]

    report = generate_ab_report(results_a, results_b, cases, "pruning_off", "pruning_on")

    assert "| Infra retries used | 1 | 3 | +2 |" in report


def test_generate_ab_report_distinguishes_infra_and_generation_errors():
    cases = [make_case("case_a"), make_case("case_b")]
    results_a = [
        make_error_result("case_a", "Workflow error: Remote host terminated the handshake"),
        make_error_result("case_b", "Generated code was empty"),
    ]
    results_b = [make_result("case_a", True, 90, 1), make_result("case_b", False, 50, 1)]

    report = generate_ab_report(results_a, results_b, cases, "baseline", "candidate")

    assert "| Infra/provider errors | 1 | 0 | -1 |" in report
    assert "| Other generation errors | 1 | 0 | -1 |" in report
    assert "| case_a | html | ⚠️ | ✅ | 0/1 | 1/1 | infra 1 | - | 0 | 0 | +90.0 | +0.0s (+0.0%) |" in report
    assert "| case_b | html | ⚠️ | ❌ | 0/1 | 0/1 | generation 1 | - | 0 | 0 | +50.0 | +0.0s (+0.0%) |" in report


def test_generate_ab_report_flags_suspicious_empty_generations():
    cases = [make_case("case_a")]
    results_a = [make_result("case_a", True, 90, 1)]
    results_b = [make_suspicious_result("case_a")]

    report = generate_ab_report(results_a, results_b, cases, "baseline", "candidate")

    assert "| Suspicious empty generations | 0 | 1 | +1 |" in report
    assert "| case_a | html | ✅ | ⚠️ | 1/1 | 0/1 | - | suspicious empty 1 | 0 | 0 | -90.0 | -1.0s (-98.3%) |" in report


def test_generate_markdown_reports_infra_retries_and_error_types():
    cases = [make_case("case_a"), make_case("case_b")]
    infra_result = make_error_result(
        "case_a",
        "Workflow error: Remote host terminated the handshake",
    )
    infra_result.run_config["infra_retries_used"] = 2
    generation_result = make_error_result("case_b", "Generated code was empty")

    report = generate_markdown([infra_result, generation_result], cases)

    assert "- **Infra retries used**: 2" in report
    assert "- **Infra/provider errors**: 1" in report
    assert "- **Other generation errors**: 1" in report
    assert "| case_a | html | ⚠️ | 0/1 | 2 | infra 1 |" in report
    assert "| case_b | html | ⚠️ | 0/1 | 0 | generation 1 |" in report
    assert "**Error type**: infra/provider" in report
    assert "**Error type**: generation" in report


def test_generate_markdown_flags_suspicious_empty_generation():
    cases = [make_case("case_a")]
    suspicious = make_suspicious_result("case_a")

    report = generate_markdown([suspicious], cases)

    assert "- **Suspicious empty generations**: 1" in report
    assert "| case_a | html | ⚠️ | 0/1 | 0 | suspicious empty 1 |" in report
    assert "**Error type**: suspicious-empty-generation" in report


def test_generate_markdown_includes_separate_execution_smoke_section():
    cases = [make_case("case_a"), make_case("case_b")]
    results = [
        with_execution(make_result("case_a", True, 100, 1), True),
        with_execution(make_result("case_b", True, 100, 1), False, "console_error", "boom"),
    ]

    report = generate_markdown(results, cases)

    assert "- **Execution smoke pass rate**: 50.0% (1/2 judged runs)" in report
    assert "## Execution Smoke" in report
    assert "reported separately from structural score" in report
    assert "| case_a | 1/1 | 1/1 | 0 | - |" in report
    assert "| case_b | 1/1 | 0/1 | 0 | console_error |" in report


def test_generate_ab_report_includes_execution_smoke_without_changing_structural_summary():
    cases = [make_case("case_a")]
    results_a = [with_execution(make_result("case_a", True, 90, 1), True)]
    results_b = [with_execution(make_result("case_a", True, 90, 1), False, "missing_element")]

    report = generate_ab_report(results_a, results_b, cases, "baseline", "candidate")

    assert "| pass@1 | 100.0% | 100.0% | +0.0 pp |" in report
    assert "| Execution smoke pass rate | 100.0% (1/1) | 0.0% (0/1) | -100.0 pp |" in report
    assert "## Execution Smoke" in report
    assert "reported separately from structural pass@k" in report
    assert "| case_a | 1/1 | 0/1 (missing_element) |" in report


def test_execution_smoke_checker_errors_do_not_count_as_app_failures():
    cases = [make_case("case_a"), make_case("case_b")]
    results = [
        with_execution(make_result("case_a", True, 100, 1), True),
        with_execution(make_result("case_b", True, 100, 1), False, "checker_error", "browser missing"),
    ]

    report = generate_markdown(results, cases)

    assert "- **Execution smoke pass rate**: 100.0% (1/1 judged runs)" in report
    assert "- **Execution checker errors**: 1" in report
    assert "| case_a | 1/1 | 1/1 | 0 | - |" in report
    assert "| case_b | 0/1 | 0/0 | 1 | - |" in report


def test_ab_execution_smoke_checker_errors_do_not_count_as_app_failures():
    cases = [make_case("case_a")]
    results_a = [with_execution(make_result("case_a", True, 90, 1), True)]
    results_b = [with_execution(make_result("case_a", True, 90, 1), False, "checker_error")]

    report = generate_ab_report(results_a, results_b, cases, "baseline", "candidate")

    assert "| Execution smoke pass rate | 100.0% (1/1) | n/a | n/a |" in report
    assert "| Execution checker errors | 0 | 1 | +1 |" in report
    assert "| case_a | 1/1 | checker_error 1 |" in report


def test_generate_markdown_reports_repair_separately_from_first_shot_execution():
    cases = [make_case("case_a")]
    first_shot_failed = with_execution(
        make_result("case_a", True, 100, 1),
        False,
        "console_error",
    )
    with_repair(first_shot_failed, succeeded=True, token_total=123)

    report = generate_markdown([first_shot_failed], cases)

    assert "- **Execution smoke pass rate**: 0.0% (0/1 judged runs)" in report
    assert "- **Pass after one repair (includes one repair)**: 100.0% (1/1)" in report
    assert "- **Repair uplift**: +100.0 pp (pass_after_one_repair - first_shot_execution_pass)" in report
    assert "- **Repair attempts/successes**: 1/1" in report
    assert "- **Repair generation errors**: 0" in report
    assert "- **Repair token cost**: 123" in report
    assert "## One-Shot Repair" in report
    assert "| case_a | 1 | 0/1 | 1 | 1 | 0 | 1/1 | 123 | repair_succeeded |" in report


def test_generate_ab_report_reports_pass_after_repair_with_separate_denominator():
    cases = [make_case("case_a")]
    results_a = [
        with_execution(make_result("case_a", True, 100, 1), False, "console_error")
    ]
    results_b = [
        with_repair(
            with_execution(make_result("case_a", True, 100, 1), False, "console_error"),
            succeeded=True,
            token_total=55,
        )
    ]

    report = generate_ab_report(results_a, results_b, cases, "baseline", "candidate")

    assert "| Execution smoke pass rate | 0.0% (0/1) | 0.0% (0/1) | +0.0 pp |" in report
    assert "| Pass after one repair (includes one repair) | - | 100.0% (1/1) | - |" in report
    assert "| Repair uplift | - | +100.0 pp | - |" in report
    assert "| Repair attempts/successes | 0/0 | 1/1 | +1 successes |" in report
    assert "| Repair generation errors | 0 | 0 | +0 |" in report
    assert "| Repair token cost | 0 | 55 | +55 |" in report


def test_repair_generation_errors_are_reported_separately():
    cases = [make_case("case_a")]
    result = with_repair(
        with_execution(make_result("case_a", True, 100, 1), False, "console_error"),
        succeeded=False,
        reason="repair_generation_error",
    )

    report = generate_markdown([result], cases)

    assert "- **Execution smoke pass rate**: 0.0% (0/1 judged runs)" in report
    assert "- **Pass after one repair (includes one repair)**: 0.0% (0/1)" in report
    assert "- **Repair attempts/successes**: 1/0" in report
    assert "- **Repair generation errors**: 1" in report
    assert "| case_a | 1 | 0/1 | 1 | 0 | 1 | 0/1 | 0 | repair_generation_error |" in report
