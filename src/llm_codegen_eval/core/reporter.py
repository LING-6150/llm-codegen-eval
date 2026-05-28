"""Generate markdown reports from benchmark results."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .case import EvalCase
from .result import EvalResult
from . import stats

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
    lines.append(f"- **Avg score**: {summary.get('avg_score', 0):.1f}/100")
    lines.append(f"- **Avg duration**: {summary.get('avg_duration_ms', 0)/1000:.1f}s")
    if summary.get("avg_review_score") is not None:
        lines.append(f"- **Avg review score (Zhipu)**: {summary['avg_review_score']:.1f}/100")
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
    lines.append("| Case ID | Type | Passed | Stability | Score | Required | Optional | Duration | Review |")
    lines.append("|---------|------|--------|-----------|-------|----------|----------|----------|--------|")
    for case_id, case_results in grouped_results.items():
        best = max(case_results, key=lambda r: r.score)
        case = case_map.get(case_id)
        type_str = case.code_type.value if case else "?"
        pass_str = "✅" if any(r.passed for r in case_results) else ("⚠️" if any(r.error for r in case_results) else "❌")
        stability_str = stability.get(case_id, {}).get("label", "-")
        avg_score = sum(r.score for r in case_results) / len(case_results)
        avg_duration_ms = sum(r.generation_duration_ms for r in case_results) / len(case_results)
        review_scores = [r.review_score for r in case_results if r.review_score is not None]
        review_str = f"{sum(review_scores) / len(review_scores):.1f}" if review_scores else "-"
        lines.append(
            f"| {case_id} | {type_str} | {pass_str} | {stability_str} | "
            f"{avg_score:.1f}/100 (best {best.score}) | {best.required_passed}/{best.required_total} | "
            f"{best.optional_passed}/{best.optional_total} | "
            f"{avg_duration_ms/1000:.1f}s | {review_str} |"
        )
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
                lines.append(f"**Error**: `{r.error[:200]}`")
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

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | A: " + name_a + " | B: " + name_b + " | Delta (B - A) |")
    lines.append("|--------|------|------|---------------|")
    lines.append(
        f"| pass@{k} | {pass_a['pass_rate']:.1%} | {pass_b['pass_rate']:.1%} | "
        f"{_format_percent_delta(pass_b['pass_rate'] - pass_a['pass_rate'])} |"
    )
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
        f"{(summary_b.get('avg_duration_ms', 0) - summary_a.get('avg_duration_ms', 0))/1000:+.1f}s |"
    )
    lines.append("")

    lines.append("## Per-Case Diff")
    lines.append("")
    lines.append("| Case ID | Type | A Pass | B Pass | A Stability | B Stability | Avg Score Delta | Avg Duration Delta |")
    lines.append("|---------|------|--------|--------|-------------|-------------|-----------------|--------------------|")

    for case in cases:
        a_runs = grouped_a.get(case.case_id, [])
        b_runs = grouped_b.get(case.case_id, [])
        a_pass = any(r.passed for r in a_runs)
        b_pass = any(r.passed for r in b_runs)
        a_score = _avg([r.score for r in a_runs])
        b_score = _avg([r.score for r in b_runs])
        a_duration = _avg([r.generation_duration_ms for r in a_runs])
        b_duration = _avg([r.generation_duration_ms for r in b_runs])
        lines.append(
            f"| {case.case_id} | {case.code_type.value} | {_status(a_pass, a_runs)} | {_status(b_pass, b_runs)} | "
            f"{stability_a.get(case.case_id, {}).get('label', '-')} | "
            f"{stability_b.get(case.case_id, {}).get('label', '-')} | "
            f"{b_score - a_score:+.1f} | {(b_duration - a_duration)/1000:+.1f}s |"
        )

    return "\n".join(lines)


def _avg(values: list[float | int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _format_percent_delta(delta: float) -> str:
    return f"{delta * 100:+.1f} pp"


def _status(passed: bool, runs: list[EvalResult]) -> str:
    if passed:
        return "✅"
    if any(r.error for r in runs):
        return "⚠️"
    return "❌"
