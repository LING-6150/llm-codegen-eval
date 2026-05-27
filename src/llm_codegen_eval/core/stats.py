"""Statistics computation for benchmark results."""

from collections import defaultdict
from typing import Any
from .result import EvalResult

def compute_summary(results: list[EvalResult]) -> dict[str, Any]:
    """Compute overall summary stats."""
    total = len(results)
    if total == 0:
        return {"total": 0}

    passed = sum(1 for r in results if r.passed)
    errored = sum(1 for r in results if r.error is not None)

    avg_score = sum(r.score for r in results) / total
    avg_duration_ms = sum(r.generation_duration_ms for r in results) / total

    # Only count review score from successful runs
    review_scores = [r.review_score for r in results if r.review_score is not None]
    avg_review_score = sum(review_scores) / len(review_scores) if review_scores else None

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed - errored,
        "errored": errored,
        "pass_rate": passed / total,
        "avg_score": avg_score,
        "avg_duration_ms": avg_duration_ms,
        "avg_review_score": avg_review_score,
    }

def group_by(results: list[EvalResult], key_fn) -> dict[str, list[EvalResult]]:
    """Group results by a key function."""
    grouped = defaultdict(list)
    for r in results:
        grouped[key_fn(r)].append(r)
    return dict(grouped)

def stats_per_group(
    results: list[EvalResult],
    case_map: dict[str, "EvalCase"],
    group_attr: str
) -> dict[str, dict[str, Any]]:
    """Compute stats grouped by case attribute (code_type, difficulty, tags)."""
    from .case import EvalCase

    grouped: dict[str, list[EvalResult]] = defaultdict(list)

    for r in results:
        case = case_map.get(r.case_id)
        if case is None:
            continue

        attr_value = getattr(case, group_attr)
        # Handle enum
        if hasattr(attr_value, "value"):
            key = attr_value.value
        elif isinstance(attr_value, list):
            # tags is a list — count each tag separately
            for tag in attr_value:
                grouped[tag].append(r)
            continue
        else:
            key = str(attr_value)

        grouped[key].append(r)

    return {k: compute_summary(v) for k, v in grouped.items()}

def find_failures(results: list[EvalResult]) -> list[EvalResult]:
    """Get all non-passing results sorted by score ascending."""
    failures = [r for r in results if not r.passed]
    return sorted(failures, key=lambda r: r.score)
