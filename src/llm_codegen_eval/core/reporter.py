"""Generate markdown reports from benchmark results."""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .case import EvalCase
from .result import EvalResult
from . import stats
from .batch_runner import is_infra_error
from .metrics import TokenSummary

def generate_markdown(
    results: list[EvalResult],
    cases: list[EvalCase],
    config_name: str = "baseline",
    config_details: Optional[dict] = None
) -> str:
    """Generate a comprehensive markdown report."""

    case_map = {c.case_id: c for c in cases}
    summary = stats.compute_summary(results)
    grouped_results = stats.results_by_case(results)
    runs_per_case = max((len(v) for v in grouped_results.values()), default=1)
    pass_at_1 = stats.pass_at_k(results, 1)
    pass_at_k = stats.pass_at_k(results, runs_per_case)
    stability = stats.stability_by_case(results)
    infra_retries_used = _infra_retries_used(results)
    infra_errors = _infra_errors(results)
    non_infra_errors = _non_infra_errors(results)
    suspicious_empty = _suspicious_empty_generations(results)
    execution_summary = _execution_summary(results)
    repair_summary = _repair_summary(results)

    lines = []

    # === Header ===
    lines.append(f"# Eval Report — {config_name}")
    lines.append("")
    lines.append(f"**Run at**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total cases**: {len(grouped_results) or summary['total']}")
    if runs_per_case > 1:
        lines.append(f"**Total runs**: {summary['total']}")
    if config_details:
        for k, v in config_details.items():
            lines.append(f"**{k}**: {v}")
    lines.append("")

    # === Summary ===
    lines.append("## Summary")
    lines.append("")
    if runs_per_case > 1:
        lines.append(
            f"- **pass@{runs_per_case}**: {pass_at_k['pass_rate']:.1%} "
            f"({pass_at_k['passed_cases']}/{pass_at_k['total_cases']} cases)"
        )
        lines.append(
            f"- **pass@1**: {pass_at_1['pass_rate']:.1%} "
            f"({pass_at_1['passed_cases']}/{pass_at_1['total_cases']} cases)"
        )
        lines.append(f"- **Run-level pass rate**: {summary.get('pass_rate', 0):.1%} ({summary['passed']}/{summary['total']} runs)")
    else:
        lines.append(f"- **pass@1**: {summary.get('pass_rate', 0):.1%} ({summary['passed']}/{summary['total']})")
    lines.append(f"- **Failed**: {summary.get('failed', 0)}")
    lines.append(f"- **Errored**: {summary.get('errored', 0)} (generation/network errors)")
    lines.append(f"- **Infra retries used**: {infra_retries_used}")
    lines.append(f"- **Infra/provider errors**: {len(infra_errors)}")
    lines.append(f"- **Other generation errors**: {len(non_infra_errors)}")
    lines.append(f"- **Suspicious empty generations**: {len(suspicious_empty)}")
    lines.append(f"- **Avg score**: {summary.get('avg_score', 0):.1f}/100")
    lines.append(f"- **Avg duration**: {summary.get('avg_duration_ms', 0)/1000:.1f}s")
    if summary.get("avg_review_score") is not None:
        lines.append(f"- **Avg review score (Zhipu)**: {summary['avg_review_score']:.1f}/100")
    if execution_summary["enabled"]:
        lines.append(
            f"- **Execution smoke pass rate**: "
            f"{execution_summary['pass_rate']:.1%} "
            f"({execution_summary['passed']}/{execution_summary['judged']} judged runs)"
        )
        lines.append(f"- **Execution checker errors**: {execution_summary['checker_errors']}")
    if repair_summary["enabled"]:
        lines.append(
            f"- **Pass after one repair (includes one repair)**: "
            f"{_format_repair_pass_after(repair_summary)}"
        )
        lines.append(
            f"- **Repair uplift**: {_format_percent_delta(repair_summary['repair_uplift'])} "
            "(pass_after_one_repair - first_shot_execution_pass)"
        )
        lines.append(
            f"- **Repair attempts/successes**: "
            f"{repair_summary['attempted']}/{repair_summary['succeeded']}"
        )
        lines.append(f"- **Repair generation errors**: {repair_summary['generation_errors']}")
        lines.append(f"- **Repair token cost**: {repair_summary['token_cost']:,}")
    lines.append("")

    # === Per code_type ===
    lines.append("## By Code Type")
    lines.append("")
    lines.append("| Type | Cases | Pass | Pass Rate | Avg Score | Avg Duration |")
    lines.append("|------|-------|------|-----------|-----------|--------------|")
    type_stats = stats.stats_per_group(results, case_map, "code_type")
    for code_type, s in sorted(type_stats.items()):
        lines.append(
            f"| {code_type} | {s['total']} | {s['passed']} | "
            f"{s.get('pass_rate', 0):.1%} | {s.get('avg_score', 0):.1f} | "
            f"{s.get('avg_duration_ms', 0)/1000:.1f}s |"
        )
    lines.append("")

    # === Per difficulty ===
    lines.append("## By Difficulty")
    lines.append("")
    lines.append("| Difficulty | Cases | Pass | Pass Rate | Avg Score |")
    lines.append("|------------|-------|------|-----------|-----------|")
    diff_stats = stats.stats_per_group(results, case_map, "difficulty")
    diff_order = ["easy", "medium", "hard", "edge"]
    for diff in diff_order:
        if diff not in diff_stats:
            continue
        s = diff_stats[diff]
        lines.append(
            f"| {diff} | {s['total']} | {s['passed']} | "
            f"{s.get('pass_rate', 0):.1%} | {s.get('avg_score', 0):.1f} |"
        )
    lines.append("")

    # === Per case (detailed) ===
    lines.append("## Per-Case Results")
    lines.append("")
    lines.append("| Case ID | Type | Passed | Stability | Infra Retries | Errors | Score | Required | Optional | Duration | Review |")
    lines.append("|---------|------|--------|-----------|---------------|--------|-------|----------|----------|----------|--------|")
    for case_id, case_results in grouped_results.items():
        best = max(case_results, key=lambda r: r.score)
        case = case_map.get(case_id)
        type_str = case.code_type.value if case else "?"
        pass_str = "✅" if any(r.passed for r in case_results) else ("⚠️" if _has_error_or_suspicious(case_results) else "❌")
        stability_str = stability.get(case_id, {}).get("label", "-")
        avg_score = sum(r.score for r in case_results) / len(case_results)
        avg_duration_ms = sum(r.generation_duration_ms for r in case_results) / len(case_results)
        review_scores = [r.review_score for r in case_results if r.review_score is not None]
        review_str = f"{sum(review_scores) / len(review_scores):.1f}" if review_scores else "-"
        case_infra_retries = _infra_retries_used(case_results)
        error_str = _error_summary(case_results)
        lines.append(
            f"| {case_id} | {type_str} | {pass_str} | {stability_str} | "
            f"{case_infra_retries} | {error_str} | "
            f"{avg_score:.1f}/100 (best {best.score}) | {best.required_passed}/{best.required_total} | "
            f"{best.optional_passed}/{best.optional_total} | "
            f"{avg_duration_ms/1000:.1f}s | {review_str} |"
        )
    lines.append("")

    if execution_summary["enabled"]:
        lines.extend(_format_execution_smoke_section(results))
        lines.append("")

    if repair_summary["enabled"]:
        lines.extend(_format_repair_section(results))
        lines.append("")

    # === Failures ===
    failures = stats.find_failures(results)
    if failures:
        lines.append("## Failure Analysis")
        lines.append("")
        for r in failures[:10]:  # Top 10 worst
            case = case_map.get(r.case_id)
            lines.append(f"### {r.case_id}: score={r.score}/100")
            if case:
                lines.append(f"**Prompt**: {case.prompt[:120]}")
            if r.error:
                lines.append(f"**Error type**: {_error_type(r)}")
                lines.append(f"**Error**: `{r.error[:200]}`")
            elif _is_suspicious_empty_generation(r):
                lines.append("**Error type**: suspicious-empty-generation")
                lines.append("**Error**: empty code with near-zero generation duration")
            if r.required_failed:
                lines.append("**Failed required checks**:")
                for check in r.required_failed:
                    lines.append(f"- {check.description}")
            if r.forbidden_found:
                lines.append(f"**Forbidden patterns found**: {r.forbidden_found}")
            lines.append("")

    return "\n".join(lines)

def save_report(
    content: str,
    output_dir: Path = Path("reports"),
    filename_prefix: str = "baseline"
) -> Path:
    """Save report to a timestamped file."""
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.md"
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def generate_ab_report(
    results_a: list[EvalResult],
    results_b: list[EvalResult],
    cases: list[EvalCase],
    name_a: str,
    name_b: str,
    config_details: Optional[dict] = None,
    token_summary_a: Optional[TokenSummary] = None,
    token_summary_b: Optional[TokenSummary] = None,
) -> str:
    """Generate a markdown comparison report for two benchmark configurations."""

    case_map = {c.case_id: c for c in cases}
    grouped_a = stats.results_by_case(results_a)
    grouped_b = stats.results_by_case(results_b)
    runs_a = max((len(v) for v in grouped_a.values()), default=1)
    runs_b = max((len(v) for v in grouped_b.values()), default=1)
    k = min(runs_a, runs_b)

    summary_a = stats.compute_summary(results_a)
    summary_b = stats.compute_summary(results_b)
    pass_a = stats.pass_at_k(results_a, k)
    pass_b = stats.pass_at_k(results_b, k)
    pass1_a = stats.pass_at_k(results_a, 1)
    pass1_b = stats.pass_at_k(results_b, 1)
    stability_a = stats.stability_by_case(results_a)
    stability_b = stats.stability_by_case(results_b)
    pass_delta = pass_b["pass_rate"] - pass_a["pass_rate"]
    score_delta = summary_b.get("avg_score", 0) - summary_a.get("avg_score", 0)
    duration_delta_ms = summary_b.get("avg_duration_ms", 0) - summary_a.get("avg_duration_ms", 0)
    duration_delta_pct = _pct_change(summary_a.get("avg_duration_ms", 0), summary_b.get("avg_duration_ms", 0))
    retries_a = _infra_retries_used(results_a)
    retries_b = _infra_retries_used(results_b)
    infra_errors_a = len(_infra_errors(results_a))
    infra_errors_b = len(_infra_errors(results_b))
    generation_errors_a = len(_non_infra_errors(results_a))
    generation_errors_b = len(_non_infra_errors(results_b))
    suspicious_a = len(_suspicious_empty_generations(results_a))
    suspicious_b = len(_suspicious_empty_generations(results_b))
    execution_a = _execution_summary(results_a)
    execution_b = _execution_summary(results_b)
    repair_a = _repair_summary(results_a)
    repair_b = _repair_summary(results_b)
    improvements, regressions, unstable = _classify_ab_cases(cases, grouped_a, grouped_b, stability_a, stability_b)

    lines = []
    lines.append(f"# A/B Eval Report — {name_a} vs {name_b}")
    lines.append("")
    lines.append(f"**Run at**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Cases**: {len(case_map)}")
    lines.append(f"**Compared k**: {k}")
    if config_details:
        for key, value in config_details.items():
            lines.append(f"**{key}**: {value}")
    lines.append("")

    lines.append("## Winner Summary")
    lines.append("")
    lines.append(f"- **pass@{k} delta (B - A)**: {_format_percent_delta(pass_delta)}")
    lines.append(f"- **Avg score delta (B - A)**: {score_delta:+.1f}")
    lines.append(f"- **Avg duration delta (B - A)**: {duration_delta_ms/1000:+.1f}s ({duration_delta_pct:+.1f}%)")
    if pass_delta > 0:
        lines.append(f"- **Pass-rate winner**: {name_b}")
    elif pass_delta < 0:
        lines.append(f"- **Pass-rate winner**: {name_a}")
    else:
        lines.append("- **Pass-rate winner**: tie")
    if duration_delta_ms < 0:
        lines.append(f"- **Latency winner**: {name_b}")
    elif duration_delta_ms > 0:
        lines.append(f"- **Latency winner**: {name_a}")
    else:
        lines.append("- **Latency winner**: tie")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | A: " + name_a + " | B: " + name_b + " | Delta (B - A) |")
    lines.append("|--------|------|------|---------------|")
    lines.append(
        f"| pass@{k} | {pass_a['pass_rate']:.1%} | {pass_b['pass_rate']:.1%} | "
        f"{_format_percent_delta(pass_b['pass_rate'] - pass_a['pass_rate'])} |"
    )
    if k != 1:
        lines.append(
            f"| pass@1 | {pass1_a['pass_rate']:.1%} | {pass1_b['pass_rate']:.1%} | "
            f"{_format_percent_delta(pass1_b['pass_rate'] - pass1_a['pass_rate'])} |"
        )
    lines.append(
        f"| Run-level pass rate | {summary_a.get('pass_rate', 0):.1%} | "
        f"{summary_b.get('pass_rate', 0):.1%} | "
        f"{_format_percent_delta(summary_b.get('pass_rate', 0) - summary_a.get('pass_rate', 0))} |"
    )
    lines.append(
        f"| Avg score | {summary_a.get('avg_score', 0):.1f} | {summary_b.get('avg_score', 0):.1f} | "
        f"{summary_b.get('avg_score', 0) - summary_a.get('avg_score', 0):+.1f} |"
    )
    lines.append(
        f"| Avg duration | {summary_a.get('avg_duration_ms', 0)/1000:.1f}s | "
        f"{summary_b.get('avg_duration_ms', 0)/1000:.1f}s | "
        f"{duration_delta_ms/1000:+.1f}s ({duration_delta_pct:+.1f}%) |"
    )
    lines.append(
        f"| Infra retries used | {retries_a} | {retries_b} | "
        f"{_format_int_delta(retries_b - retries_a)} |"
    )
    lines.append(
        f"| Infra/provider errors | {infra_errors_a} | {infra_errors_b} | "
        f"{_format_int_delta(infra_errors_b - infra_errors_a)} |"
    )
    lines.append(
        f"| Other generation errors | {generation_errors_a} | {generation_errors_b} | "
        f"{_format_int_delta(generation_errors_b - generation_errors_a)} |"
    )
    lines.append(
        f"| Suspicious empty generations | {suspicious_a} | {suspicious_b} | "
        f"{_format_int_delta(suspicious_b - suspicious_a)} |"
    )
    if execution_a["enabled"] or execution_b["enabled"]:
        lines.append(
            f"| Execution smoke pass rate | {_format_execution_rate(execution_a)} | "
            f"{_format_execution_rate(execution_b)} | "
            f"{_format_execution_rate_delta(execution_a, execution_b)} |"
        )
        lines.append(
            f"| Execution checker errors | {execution_a['checker_errors']} | "
            f"{execution_b['checker_errors']} | "
            f"{_format_int_delta(execution_b['checker_errors'] - execution_a['checker_errors'])} |"
        )
    if repair_a["enabled"] or repair_b["enabled"]:
        lines.append(
            f"| Pass after one repair (includes one repair) | "
            f"{_format_repair_pass_after(repair_a)} | "
            f"{_format_repair_pass_after(repair_b)} | "
            f"{_format_repair_rate_delta(repair_a, repair_b)} |"
        )
        lines.append(
            f"| Repair uplift | {_format_repair_uplift(repair_a)} | "
            f"{_format_repair_uplift(repair_b)} | "
            f"{_format_repair_uplift_delta(repair_a, repair_b)} |"
        )
        lines.append(
            f"| Repair attempts/successes | "
            f"{repair_a['attempted']}/{repair_a['succeeded']} | "
            f"{repair_b['attempted']}/{repair_b['succeeded']} | "
            f"{_format_int_delta(repair_b['succeeded'] - repair_a['succeeded'])} successes |"
        )
        lines.append(
            f"| Repair generation errors | {repair_a['generation_errors']} | "
            f"{repair_b['generation_errors']} | "
            f"{_format_int_delta(repair_b['generation_errors'] - repair_a['generation_errors'])} |"
        )
        lines.append(
            f"| Repair token cost | {repair_a['token_cost']:,} | "
            f"{repair_b['token_cost']:,} | "
            f"{_format_int_delta(repair_b['token_cost'] - repair_a['token_cost'])} |"
        )
    lines.append("")

    if token_summary_a and token_summary_b:
        lines.extend(_format_token_summary(token_summary_a, token_summary_b, name_a, name_b))
    lines.append("")

    if execution_a["enabled"] or execution_b["enabled"]:
        lines.extend(_format_ab_execution_smoke_section(results_a, results_b, cases, name_a, name_b))
        lines.append("")

    if repair_a["enabled"] or repair_b["enabled"]:
        lines.extend(_format_ab_repair_section(results_a, results_b, cases, name_a, name_b))
        lines.append("")

    lines.append("## Improvements")
    lines.append("")
    if improvements:
        for case_id in improvements:
            lines.append(f"- `{case_id}`: A failed, B passed")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Regressions")
    lines.append("")
    if regressions:
        for case_id in regressions:
            lines.append(f"- `{case_id}`: A passed, B failed")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Unstable Cases")
    lines.append("")
    if unstable:
        for case_id, a_label, b_label in unstable:
            lines.append(f"- `{case_id}`: A {a_label}, B {b_label}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Per-Case Diff")
    lines.append("")
    lines.append("| Case ID | Type | A Pass | B Pass | A Stability | B Stability | A Errors | B Errors | A Infra Retries | B Infra Retries | Avg Score Delta | Avg Duration Delta |")
    lines.append("|---------|------|--------|--------|-------------|-------------|----------|----------|-----------------|-----------------|-----------------|--------------------|")

    for case in cases:
        a_runs = grouped_a.get(case.case_id, [])
        b_runs = grouped_b.get(case.case_id, [])
        a_pass = any(r.passed for r in a_runs)
        b_pass = any(r.passed for r in b_runs)
        a_score = _avg([r.score for r in a_runs])
        b_score = _avg([r.score for r in b_runs])
        a_duration = _avg([r.generation_duration_ms for r in a_runs])
        b_duration = _avg([r.generation_duration_ms for r in b_runs])
        duration_pct = _pct_change(a_duration, b_duration)
        lines.append(
            f"| {case.case_id} | {case.code_type.value} | {_status(a_pass, a_runs)} | {_status(b_pass, b_runs)} | "
            f"{stability_a.get(case.case_id, {}).get('label', '-')} | "
            f"{stability_b.get(case.case_id, {}).get('label', '-')} | "
            f"{_error_summary(a_runs)} | {_error_summary(b_runs)} | "
            f"{_infra_retries_used(a_runs)} | {_infra_retries_used(b_runs)} | "
            f"{b_score - a_score:+.1f} | {(b_duration - a_duration)/1000:+.1f}s ({duration_pct:+.1f}%) |"
        )

    return "\n".join(lines)


def _avg(values: list[float | int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _infra_retries_used(results: list[EvalResult]) -> int:
    return sum(int(r.run_config.get("infra_retries_used", 0) or 0) for r in results)


def _infra_errors(results: list[EvalResult]) -> list[EvalResult]:
    return [r for r in results if is_infra_error(r)]


def _non_infra_errors(results: list[EvalResult]) -> list[EvalResult]:
    return [r for r in results if r.error and not is_infra_error(r)]


def _suspicious_empty_generations(results: list[EvalResult]) -> list[EvalResult]:
    return [r for r in results if _is_suspicious_empty_generation(r)]


def _is_suspicious_empty_generation(result: EvalResult) -> bool:
    return (
        not result.passed
        and result.score == 0
        and not result.error
        and result.generation_duration_ms < 1000
        and not result.generated_code.strip()
    )


def _has_error_or_suspicious(results: list[EvalResult]) -> bool:
    return any(r.error or _is_suspicious_empty_generation(r) for r in results)


def _error_type(result: EvalResult) -> str:
    if not result.error:
        if _is_suspicious_empty_generation(result):
            return "suspicious-empty-generation"
        return "-"
    if is_infra_error(result):
        return "infra/provider"
    return "generation"


def _error_summary(results: list[EvalResult]) -> str:
    infra_count = len(_infra_errors(results))
    generation_count = len(_non_infra_errors(results))
    suspicious_count = len(_suspicious_empty_generations(results))
    if infra_count == 0 and generation_count == 0 and suspicious_count == 0:
        return "-"

    parts = []
    if infra_count:
        parts.append(f"infra {infra_count}")
    if generation_count:
        parts.append(f"generation {generation_count}")
    if suspicious_count:
        parts.append(f"suspicious empty {suspicious_count}")
    return ", ".join(parts)


def _format_percent_delta(delta: float) -> str:
    return f"{delta * 100:+.1f} pp"


def _status(passed: bool, runs: list[EvalResult]) -> str:
    if passed:
        return "✅"
    if _has_error_or_suspicious(runs):
        return "⚠️"
    return "❌"


def _pct_change(before: float, after: float) -> float:
    if before == 0:
        return 0.0
    return (after - before) / before * 100


def _classify_ab_cases(
    cases: list[EvalCase],
    grouped_a: dict[str, list[EvalResult]],
    grouped_b: dict[str, list[EvalResult]],
    stability_a: dict[str, dict[str, Any]],
    stability_b: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], list[tuple[str, str, str]]]:
    improvements = []
    regressions = []
    unstable = []

    for case in cases:
        a_runs = grouped_a.get(case.case_id, [])
        b_runs = grouped_b.get(case.case_id, [])
        a_pass = any(r.passed for r in a_runs)
        b_pass = any(r.passed for r in b_runs)

        if not a_pass and b_pass:
            improvements.append(case.case_id)
        elif a_pass and not b_pass:
            regressions.append(case.case_id)

        a_info = stability_a.get(case.case_id)
        b_info = stability_b.get(case.case_id)
        a_unstable = a_info and 0 < a_info["passed"] < a_info["total"]
        b_unstable = b_info and 0 < b_info["passed"] < b_info["total"]
        if a_unstable or b_unstable:
            unstable.append((
                case.case_id,
                a_info["label"] if a_info else "-",
                b_info["label"] if b_info else "-",
            ))

    return improvements, regressions, unstable


def _format_token_summary(
    token_summary_a: TokenSummary,
    token_summary_b: TokenSummary,
    name_a: str,
    name_b: str,
) -> list[str]:
    lines = [
        "## Token Usage",
        "",
        "Prometheus counter deltas captured around each sequential config run.",
        "Attribution assumes no other AI requests used the same appId during this A/B run.",
        "",
        f"| Metric | A: {name_a} | B: {name_b} | Delta (B - A) |",
        "|--------|------|------|---------------|",
    ]

    for key, label in [("input", "Input tokens"), ("output", "Output tokens"), ("total", "Total tokens")]:
        a_value = int(token_summary_a.get(key, 0))
        b_value = int(token_summary_b.get(key, 0))
        lines.append(
            f"| {label} | {_format_int(a_value)} | {_format_int(b_value)} | "
            f"{_format_int_delta(b_value - a_value)} ({_pct_change(a_value, b_value):+.1f}%) |"
        )

    by_agent_a = token_summary_a.get("by_agent", {})
    by_agent_b = token_summary_b.get("by_agent", {})
    if isinstance(by_agent_a, dict) and isinstance(by_agent_b, dict) and (by_agent_a or by_agent_b):
        lines.append("")
        lines.append("### By Agent")
        lines.append("")
        lines.append(f"| Agent | A: {name_a} | B: {name_b} | Delta (B - A) |")
        lines.append("|-------|------|------|---------------|")
        for agent in sorted(set(by_agent_a) | set(by_agent_b)):
            a_total = _nested_total(by_agent_a, agent)
            b_total = _nested_total(by_agent_b, agent)
            lines.append(
                f"| {agent} | {_format_int(a_total)} | {_format_int(b_total)} | "
                f"{_format_int_delta(b_total - a_total)} ({_pct_change(a_total, b_total):+.1f}%) |"
            )

    return lines


def _nested_total(values: dict, key: str) -> int:
    nested = values.get(key, {})
    if not isinstance(nested, dict):
        return 0
    return int(nested.get("total", 0))


def _format_int(value: int) -> str:
    return f"{value:,}"


def _format_int_delta(value: int) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):,}"


def _execution_summary(results: list[EvalResult]) -> dict[str, Any]:
    smoke_results = [r.execution_smoke for r in results if r.execution_smoke is not None]
    if not smoke_results:
        return {
            "enabled": False,
            "total": 0,
            "applicable": 0,
            "judged": 0,
            "passed": 0,
            "failed": 0,
            "checker_errors": 0,
            "not_applicable": 0,
            "pass_rate": 0.0,
        }

    applicable = [r for r in smoke_results if r.applicable]
    checker_errors = [r for r in applicable if r.failure_type == "checker_error"]
    judged = [r for r in smoke_results if _is_execution_judged(r)]
    passed = [r for r in judged if r.passed]
    return {
        "enabled": True,
        "total": len(smoke_results),
        "applicable": len(applicable),
        "judged": len(judged),
        "passed": len(passed),
        "failed": len(judged) - len(passed),
        "checker_errors": len(checker_errors),
        "not_applicable": len(smoke_results) - len(applicable),
        "pass_rate": len(passed) / len(judged) if judged else 0.0,
    }


def _format_execution_rate(summary: dict[str, Any]) -> str:
    if not summary["enabled"]:
        return "-"
    if summary["judged"] == 0:
        return "n/a"
    return f"{summary['pass_rate']:.1%} ({summary['passed']}/{summary['judged']})"


def _format_execution_rate_delta(summary_a: dict[str, Any], summary_b: dict[str, Any]) -> str:
    if not summary_a["enabled"] or not summary_b["enabled"]:
        return "-"
    if summary_a["judged"] == 0 or summary_b["judged"] == 0:
        return "n/a"
    return _format_percent_delta(summary_b["pass_rate"] - summary_a["pass_rate"])


def _repair_summary(results: list[EvalResult]) -> dict[str, Any]:
    repair_results = [r for r in results if r.repair_summary is not None]
    if not repair_results:
        return {
            "enabled": False,
            "judged": 0,
            "first_shot_passed": 0,
            "pass_after_repair": 0,
            "first_shot_rate": 0.0,
            "pass_after_rate": 0.0,
            "repair_uplift": 0.0,
            "attempted": 0,
            "succeeded": 0,
            "generation_errors": 0,
            "token_cost": 0,
        }

    judged_results = _repair_judged_results(results)
    first_shot_passed = sum(
        1 for result in judged_results
        if result.execution_smoke is not None and result.execution_smoke.passed
    )
    pass_after_repair = sum(
        1 for result in judged_results
        if (
            result.execution_smoke is not None
            and result.execution_smoke.passed
        ) or (
            result.repair_summary is not None
            and result.repair_summary.succeeded
        )
    )
    attempted = sum(
        1 for result in results
        if _is_effective_repair_attempt(result.repair_summary)
    )
    succeeded = sum(
        1 for result in results
        if result.repair_summary is not None and result.repair_summary.succeeded
    )
    generation_errors = sum(
        1 for result in results
        if (
            result.repair_summary is not None
            and result.repair_summary.reason == "repair_generation_error"
        )
    )
    token_cost = sum(
        int(result.repair_summary.token_summary.get("total", 0))
        for result in results
        if result.repair_summary is not None and result.repair_summary.token_summary
    )
    judged = len(judged_results)
    first_rate = first_shot_passed / judged if judged else 0.0
    pass_after_rate = pass_after_repair / judged if judged else 0.0
    return {
        "enabled": True,
        "judged": judged,
        "first_shot_passed": first_shot_passed,
        "pass_after_repair": pass_after_repair,
        "first_shot_rate": first_rate,
        "pass_after_rate": pass_after_rate,
        "repair_uplift": pass_after_rate - first_rate,
        "attempted": attempted,
        "succeeded": succeeded,
        "generation_errors": generation_errors,
        "token_cost": token_cost,
    }


def _is_execution_judged(smoke: Any) -> bool:
    return bool(smoke is not None and smoke.applicable and smoke.failure_type != "checker_error")


def _repair_judged_results(results: list[EvalResult]) -> list[EvalResult]:
    return [result for result in results if _is_execution_judged(result.execution_smoke)]


def _is_effective_repair_attempt(summary: Any) -> bool:
    """A genuine repair attempt that reached judging.

    Generation/infra failures (``repair_generation_error``) are excluded so the
    succeeded/attempted efficacy ratio is not diluted by infra noise; they are
    surfaced separately via the generation-errors count.
    """
    return bool(
        summary is not None
        and summary.attempted
        and summary.reason != "repair_generation_error"
    )


def _format_repair_pass_after(summary: dict[str, Any]) -> str:
    if not summary["enabled"]:
        return "-"
    if summary["judged"] == 0:
        return "n/a"
    return (
        f"{summary['pass_after_rate']:.1%} "
        f"({summary['pass_after_repair']}/{summary['judged']})"
    )


def _format_repair_uplift(summary: dict[str, Any]) -> str:
    if not summary["enabled"]:
        return "-"
    if summary["judged"] == 0:
        return "n/a"
    return _format_percent_delta(summary["repair_uplift"])


def _format_repair_rate_delta(summary_a: dict[str, Any], summary_b: dict[str, Any]) -> str:
    if not summary_a["enabled"] or not summary_b["enabled"]:
        return "-"
    if summary_a["judged"] == 0 or summary_b["judged"] == 0:
        return "n/a"
    return _format_percent_delta(summary_b["pass_after_rate"] - summary_a["pass_after_rate"])


def _format_repair_uplift_delta(summary_a: dict[str, Any], summary_b: dict[str, Any]) -> str:
    if not summary_a["enabled"] or not summary_b["enabled"]:
        return "-"
    if summary_a["judged"] == 0 or summary_b["judged"] == 0:
        return "n/a"
    return _format_percent_delta(summary_b["repair_uplift"] - summary_a["repair_uplift"])


def _format_execution_smoke_section(results: list[EvalResult]) -> list[str]:
    grouped = stats.results_by_case(results)
    lines = [
        "## Execution Smoke",
        "",
        "Smoke-level runtime/build validation is reported separately from structural score.",
        "",
        "| Case ID | Judged Runs | Passed | Checker Errors | App Failure Types |",
        "|---------|-------------|--------|----------------|-------------------|",
    ]
    for case_id, case_results in grouped.items():
        smoke = [r.execution_smoke for r in case_results if r.execution_smoke is not None]
        applicable = [r for r in smoke if r.applicable]
        checker_errors = [r for r in applicable if r.failure_type == "checker_error"]
        judged = [r for r in smoke if _is_execution_judged(r)]
        passed = [r for r in judged if r.passed]
        failure_types = sorted({
            r.failure_type
            for r in judged
            if not r.passed and r.failure_type
        })
        lines.append(
            f"| {case_id} | {len(judged)}/{len(smoke)} | "
            f"{len(passed)}/{len(judged)} | {len(checker_errors)} | "
            f"{', '.join(failure_types) if failure_types else '-'} |"
        )
    return lines


def _format_repair_section(results: list[EvalResult]) -> list[str]:
    grouped = stats.results_by_case(results)
    lines = [
        "## One-Shot Repair",
        "",
        "Repair results are reported separately from first-shot structural pass@k. "
        "`pass_after_one_repair` uses the same judged denominator as first-shot execution smoke.",
        "",
        "| Case ID | First-Shot Judged | First-Shot Passed | Repair Attempted | Repair Succeeded | Repair Generation Errors | Pass After One Repair | Repair Token Cost | Reasons |",
        "|---------|-------------------|-------------------|------------------|------------------|--------------------------|-----------------------|-------------------|---------|",
    ]
    for case_id, case_results in grouped.items():
        judged = _repair_judged_results(case_results)
        first_passed = sum(
            1 for result in judged
            if result.execution_smoke is not None and result.execution_smoke.passed
        )
        attempted = sum(
            1 for result in case_results
            if _is_effective_repair_attempt(result.repair_summary)
        )
        succeeded = sum(
            1 for result in case_results
            if result.repair_summary is not None and result.repair_summary.succeeded
        )
        generation_errors = sum(
            1 for result in case_results
            if (
                result.repair_summary is not None
                and result.repair_summary.reason == "repair_generation_error"
            )
        )
        pass_after = sum(
            1 for result in judged
            if (
                result.execution_smoke is not None
                and result.execution_smoke.passed
            ) or (
                result.repair_summary is not None
                and result.repair_summary.succeeded
            )
        )
        token_cost = sum(
            int(result.repair_summary.token_summary.get("total", 0))
            for result in case_results
            if result.repair_summary is not None and result.repair_summary.token_summary
        )
        reasons = sorted({
            result.repair_summary.reason
            for result in case_results
            if result.repair_summary is not None and result.repair_summary.reason
        })
        lines.append(
            f"| {case_id} | {len(judged)} | {first_passed}/{len(judged)} | "
            f"{attempted} | {succeeded} | {generation_errors} | {pass_after}/{len(judged)} | "
            f"{token_cost:,} | {', '.join(reasons) if reasons else '-'} |"
        )
    return lines


def _format_ab_execution_smoke_section(
    results_a: list[EvalResult],
    results_b: list[EvalResult],
    cases: list[EvalCase],
    name_a: str,
    name_b: str,
) -> list[str]:
    grouped_a = stats.results_by_case(results_a)
    grouped_b = stats.results_by_case(results_b)
    lines = [
        "## Execution Smoke",
        "",
        "Smoke-level runtime/build validation is reported separately from structural pass@k.",
        "",
        f"| Case ID | A: {name_a} | B: {name_b} |",
        "|---------|------|------|",
    ]
    for case in cases:
        lines.append(
            f"| {case.case_id} | {_execution_case_status(grouped_a.get(case.case_id, []))} | "
            f"{_execution_case_status(grouped_b.get(case.case_id, []))} |"
        )
    return lines


def _format_ab_repair_section(
    results_a: list[EvalResult],
    results_b: list[EvalResult],
    cases: list[EvalCase],
    name_a: str,
    name_b: str,
) -> list[str]:
    grouped_a = stats.results_by_case(results_a)
    grouped_b = stats.results_by_case(results_b)
    lines = [
        "## One-Shot Repair",
        "",
        "Pass-after-repair is shown separately and includes at most one repair attempt.",
        "",
        f"| Case ID | A: {name_a} | B: {name_b} |",
        "|---------|------|------|",
    ]
    for case in cases:
        lines.append(
            f"| {case.case_id} | {_repair_case_status(grouped_a.get(case.case_id, []))} | "
            f"{_repair_case_status(grouped_b.get(case.case_id, []))} |"
        )
    return lines


def _repair_case_status(results: list[EvalResult]) -> str:
    if not any(result.repair_summary is not None for result in results):
        return "-"
    judged = _repair_judged_results(results)
    if not judged:
        return "n/a"
    first_passed = sum(
        1 for result in judged
        if result.execution_smoke is not None and result.execution_smoke.passed
    )
    pass_after = sum(
        1 for result in judged
        if (
            result.execution_smoke is not None
            and result.execution_smoke.passed
        ) or (
            result.repair_summary is not None
            and result.repair_summary.succeeded
        )
    )
    attempted = sum(
        1 for result in results
        if _is_effective_repair_attempt(result.repair_summary)
    )
    succeeded = sum(
        1 for result in results
        if result.repair_summary is not None and result.repair_summary.succeeded
    )
    return (
        f"first {first_passed}/{len(judged)}; "
        f"after one repair {pass_after}/{len(judged)}; "
        f"repair {attempted}/{succeeded}"
    )


def _execution_case_status(results: list[EvalResult]) -> str:
    smoke = [r.execution_smoke for r in results if r.execution_smoke is not None]
    if not smoke:
        return "-"
    applicable = [r for r in smoke if r.applicable]
    if not applicable:
        return "n/a"
    checker_errors = sum(1 for r in applicable if r.failure_type == "checker_error")
    judged = [r for r in smoke if _is_execution_judged(r)]
    if not judged:
        return f"checker_error {checker_errors}" if checker_errors else "n/a"
    passed = sum(1 for r in judged if r.passed)
    failure_types = sorted({
        r.failure_type
        for r in judged
        if not r.passed and r.failure_type
    })
    suffix_parts = []
    if failure_types:
        suffix_parts.append(", ".join(failure_types))
    if checker_errors:
        suffix_parts.append(f"checker_error {checker_errors}")
    suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""
    return f"{passed}/{len(judged)}{suffix}"
