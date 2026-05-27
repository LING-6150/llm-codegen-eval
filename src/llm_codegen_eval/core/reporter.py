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

    lines = []

    # === Header ===
    lines.append(f"# Eval Report — {config_name}")
    lines.append("")
    lines.append(f"**Run at**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total cases**: {summary['total']}")
    if config_details:
        for k, v in config_details.items():
            lines.append(f"**{k}**: {v}")
    lines.append("")

    # === Summary ===
    lines.append("## Summary")
    lines.append("")
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
    lines.append("| Case ID | Type | Passed | Score | Required | Optional | Duration | Review |")
    lines.append("|---------|------|--------|-------|----------|----------|----------|--------|")
    for r in results:
        case = case_map.get(r.case_id)
        type_str = case.code_type.value if case else "?"
        pass_str = "✅" if r.passed else ("⚠️" if r.error else "❌")
        review_str = f"{r.review_score}" if r.review_score is not None else "-"
        lines.append(
            f"| {r.case_id} | {type_str} | {pass_str} | "
            f"{r.score}/100 | {r.required_passed}/{r.required_total} | "
            f"{r.optional_passed}/{r.optional_total} | "
            f"{r.generation_duration_ms/1000:.1f}s | {review_str} |"
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
