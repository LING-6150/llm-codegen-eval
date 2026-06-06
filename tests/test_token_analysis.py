from pathlib import Path

import pytest

from llm_codegen_eval.core.batch_runner import load_results
from llm_codegen_eval.core.result import EvalResult
from llm_codegen_eval.core.token_analysis import (
    analyze_token_attribution,
    render_token_attribution_markdown,
)


def result(
    case_id: str,
    total: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    by_agent: dict | None = None,
    run_index: int = 1,
    error: str | None = None,
    extra_config: dict | None = None,
    mechanism: dict | None = None,
) -> EvalResult:
    input_value = total if input_tokens is None else input_tokens
    output_value = 0 if output_tokens is None else output_tokens
    summary = {
        "input": input_value,
        "output": output_value,
        "total": total,
        "by_agent": by_agent or {
            "CodeGenAgent": {"input": input_value, "output": output_value, "total": total}
        },
    }
    run_config = {"run_index": run_index, "token_summary": summary}
    if mechanism:
        run_config["mechanism_summary"] = mechanism
    if extra_config:
        run_config.update(extra_config)
    return EvalResult(
        case_id=case_id,
        passed=error is None,
        score=100 if error is None else 0,
        required_passed=1 if error is None else 0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        total_tokens=total,
        error=error,
        run_config=run_config,
    )


def test_analyze_token_attribution_uses_per_case_mean_not_pooled_runs():
    results_a = [
        result("case_a", 100, run_index=1),
        result("case_a", 300, run_index=2),
        result("case_b", 1000, run_index=1),
    ]
    results_b = [
        result("case_a", 400, run_index=1),
        result("case_a", 800, run_index=2),
        result("case_b", 500, run_index=1),
    ]

    analysis = analyze_token_attribution(results_a, results_b)

    case_a = next(case for case in analysis.per_case if case.case_id == "case_a")
    assert case_a.a.total == 200
    assert case_a.b.total == 600
    assert case_a.a.n_runs == 2
    assert analysis.io_split.a_total == pytest.approx(600)
    assert analysis.io_split.b_total == pytest.approx(550)


def test_analyze_token_attribution_excludes_invalid_runs_and_tracks_unpaired_cases():
    results_a = [
        result("case_a", 100),
        result("case_b", 0, error="Workflow error: Remote host terminated the handshake"),
        result("case_c", 0, extra_config={"token_capture_error": "counter reset/regression"}),
    ]
    missing_summary = result("case_d", 0)
    del missing_summary.run_config["token_summary"]
    results_a.append(missing_summary)
    results_b = [result("case_a", 120), result("case_b", 140), result("case_c", 160)]

    analysis = analyze_token_attribution(results_a, results_b)

    assert analysis.validity_a.valid_token_runs == 1
    assert analysis.validity_a.excluded["infra_error"] == 1
    assert analysis.validity_a.excluded["token_capture_error"] == 1
    assert analysis.validity_a.excluded["missing_token_summary"] == 1
    assert {run.reason for run in analysis.excluded_runs} >= {
        "infra_error",
        "token_capture_error",
        "missing_token_summary",
    }
    assert analysis.paired_case_ids == ["case_a"]
    assert any(case.case_id == "case_b" and case.present_in == "b_only" for case in analysis.unpaired_cases)


def test_analyze_token_attribution_deltas_by_agent_and_io_split():
    results_a = [
        result(
            "case_a",
            100,
            input_tokens=70,
            output_tokens=30,
            by_agent={
                "CodeGenAgent": {"input": 50, "output": 20, "total": 70},
                "ReviewAgent": {"input": 20, "output": 10, "total": 30},
            },
        )
    ]
    results_b = [
        result(
            "case_a",
            150,
            input_tokens=120,
            output_tokens=30,
            by_agent={
                "CodeGenAgent": {"input": 100, "output": 20, "total": 120},
                "ReviewAgent": {"input": 20, "output": 10, "total": 30},
            },
        )
    ]

    analysis = analyze_token_attribution(results_a, results_b)

    case = analysis.per_case[0]
    assert case.delta_total == 50
    assert case.delta_total_pct == pytest.approx(50)
    assert case.delta_input == 50
    assert case.delta_output == 0
    assert case.delta_by_agent["CodeGenAgent"].input == 50
    codegen = next(agent for agent in analysis.by_agent if agent.agent == "CodeGenAgent")
    assert codegen.delta_input_pct == pytest.approx(100)
    assert analysis.io_split.input_delta_pct == pytest.approx(71.4285714)


def test_analyze_token_attribution_direction_summary_and_zero_denominator():
    results_a = [result("case_a", 100), result("case_b", 200), result("case_c", 0)]
    results_b = [result("case_a", 150), result("case_b", 100), result("case_c", 10)]

    analysis = analyze_token_attribution(results_a, results_b)

    assert analysis.direction.n_paired_cases == 3
    assert analysis.direction.n_delta_pct_cases == 2
    assert analysis.direction.cases_b_higher == 2
    assert analysis.direction.cases_b_lower == 1
    assert analysis.direction.mean_delta_pct == pytest.approx(0)
    case_c = next(case for case in analysis.per_case if case.case_id == "case_c")
    assert case_c.delta_total_pct is None


def test_analyze_token_attribution_cross_check_uses_accounted_tokens_with_retries():
    results_a = [
        result(
            "case_a",
            100,
            extra_config={"retry_token_summaries": [{"total": 25}, {"total": 5}]},
        )
    ]
    results_b = [result("case_a", 120)]

    analysis = analyze_token_attribution(
        results_a,
        results_b,
        config_token_summary_a={"total": 130},
        config_token_summary_b={"total": 121},
    )

    assert analysis.validity_a.valid_token_sum == 100
    assert analysis.validity_a.accounted_token_sum == 130
    assert analysis.validity_a.cross_check_match is True
    assert analysis.validity_b.cross_check_match is False
    assert analysis.validity_b.cross_check_diff == 1


def mechanism_summary(
    requests: int,
    prompt_chars: int,
    input_tokens: int,
) -> dict:
    return {
        "by_agent": {
            "CodeGenAgent": {
                "requests_started": requests,
                "prompt_chars": prompt_chars,
                "input_tokens": input_tokens,
                "mean_prompt_chars_per_request": prompt_chars / requests if requests else None,
                "input_tokens_per_request": input_tokens / requests if requests else None,
            }
        }
    }


def test_analyze_token_attribution_codegen_mechanism_classifies_cases():
    results_a = [
        result("more_requests", 100, mechanism=mechanism_summary(1, 1000, 100)),
        result("larger_prompt", 100, mechanism=mechanism_summary(1, 1000, 100)),
        result("tokenization", 100, mechanism=mechanism_summary(1, 1000, 100)),
        result("no_increase", 100, mechanism=mechanism_summary(1, 1000, 100)),
    ]
    results_b = [
        result("more_requests", 150, mechanism=mechanism_summary(2, 2000, 150)),
        result("larger_prompt", 150, mechanism=mechanism_summary(1, 1500, 150)),
        result("tokenization", 150, mechanism=mechanism_summary(1, 900, 150)),
        result("no_increase", 90, mechanism=mechanism_summary(1, 900, 90)),
    ]

    analysis = analyze_token_attribution(results_a, results_b)
    mechanisms = {case.case_id: case.mechanism for case in analysis.codegen_mechanism}

    assert mechanisms == {
        "larger_prompt": "larger_prompt_per_request",
        "more_requests": "more_codegen_requests",
        "no_increase": "no_codegen_input_increase",
        "tokenization": "tokenization_or_stochastic_effect",
    }
    larger_prompt = next(case for case in analysis.codegen_mechanism if case.case_id == "larger_prompt")
    assert larger_prompt.b.mean_prompt_chars_per_request == 1500


def test_analyze_token_attribution_smoke_fixture_matches_known_totals():
    fixture_dir = Path(__file__).parent / "fixtures"
    results_a = load_results(fixture_dir / "token_smoke_pruning_off_20260606_151528.json")
    results_b = load_results(fixture_dir / "token_smoke_pruning_on_20260606_151528.json")

    analysis = analyze_token_attribution(
        results_a,
        results_b,
        config_token_summary_a={"total": 20776},
        config_token_summary_b={"total": 34452},
    )

    assert analysis.validity_a.accounted_token_sum == 20776
    assert analysis.validity_b.accounted_token_sum == 34452
    assert analysis.direction.n_paired_cases == 2
    assert analysis.validity_a.cross_check_match is True
    assert analysis.validity_b.cross_check_match is True
    for case in analysis.per_case:
        assert case.delta_by_agent["CodeGenAgent"].input > 0
    multi_019 = next(case for case in analysis.per_case if case.case_id == "multi_019")
    assert multi_019.a.input == 3286
    assert multi_019.b.input == 12122


def test_render_token_attribution_markdown_includes_core_tables():
    analysis = analyze_token_attribution(
        [result("case_a", 100, mechanism=mechanism_summary(1, 1000, 100))],
        [result("case_a", 120, mechanism=mechanism_summary(1, 1500, 120))],
    )

    markdown = render_token_attribution_markdown(analysis)

    assert "# Token Attribution Analysis" in markdown
    assert "## Per-Case Token Comparison" in markdown
    assert "## By-Agent Aggregate" in markdown
    assert "## Validity & Cross-Check" in markdown
    assert "## CodeGen Mechanism" in markdown
    assert "larger_prompt_per_request" in markdown
    assert "directional only" in markdown
    assert "Delta % Cases" in markdown
