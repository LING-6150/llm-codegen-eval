"""Statistics computation for benchmark results."""

from collections import defaultdict
import math
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

def results_by_case(results: list[EvalResult]) -> dict[str, list[EvalResult]]:
    """Group repeated runs by case id, sorted by run_index when present."""
    grouped: dict[str, list[EvalResult]] = defaultdict(list)
    for r in results:
        grouped[r.case_id].append(r)

    for case_results in grouped.values():
        case_results.sort(key=lambda r: r.run_config.get("run_index", 1))

    return dict(grouped)

def pass_at_k(results: list[EvalResult], k: int) -> dict[str, Any]:
    """Compute pass@k as cases with at least one passing run in the first k runs."""
    if k < 1:
        raise ValueError("k must be >= 1")

    grouped = results_by_case(results)
    total_cases = len(grouped)
    if total_cases == 0:
        return {"k": k, "total_cases": 0, "passed_cases": 0, "pass_rate": 0}

    passed_cases = 0
    for case_results in grouped.values():
        sampled = case_results[:k]
        if any(r.passed for r in sampled):
            passed_cases += 1

    return {
        "k": k,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / total_cases,
    }


def estimate_pass_at_k(n: int, c: int, k: int) -> float | None:
    """Chen et al. pass@k estimate using a numerically stable product form."""
    if n <= 0 or k <= 0:
        return None
    if k > n:
        return None
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0

    product = 1.0
    for i in range(n - c + 1, n + 1):
        product *= 1.0 - (k / i)
    return 1.0 - product


def structural_pass_at_k_estimate(results: list[EvalResult], k: int) -> dict[str, Any]:
    """Average per-case unbiased structural pass@k estimates."""
    grouped = results_by_case(results)
    estimates = []
    for case_results in grouped.values():
        n = len(case_results)
        c = sum(1 for result in case_results if result.passed)
        estimate = estimate_pass_at_k(n, c, k)
        if estimate is not None:
            estimates.append(estimate)

    if not estimates:
        return {
            "k": k,
            "total_cases": len(grouped),
            "estimated_cases": 0,
            "pass_rate": None,
        }

    return {
        "k": k,
        "total_cases": len(grouped),
        "estimated_cases": len(estimates),
        "pass_rate": sum(estimates) / len(estimates),
    }


def raw_run_spread_by_case(results: list[EvalResult]) -> dict[str, dict[str, Any]]:
    """Descriptive per-case run spread for repeated runs."""
    spread = {}
    for case_id, case_results in results_by_case(results).items():
        n = len(case_results)
        if n < 2:
            continue

        token_values = [
            result.total_tokens
            for result in case_results
            if _has_first_shot_token_measurement(result)
        ]
        smoke_results = [
            result.execution_smoke
            for result in case_results
            if result.execution_smoke is not None
        ]
        smoke_judged = [
            smoke for smoke in smoke_results
            if is_execution_judged(smoke)
        ]
        smoke_passed = [smoke for smoke in smoke_judged if smoke.passed]

        spread[case_id] = {
            "n": n,
            "score": _mean_stdev([result.score for result in case_results]),
            "duration_ms": _mean_stdev([result.generation_duration_ms for result in case_results]),
            "total_tokens": _mean_stdev(token_values) if token_values else None,
            "execution_smoke": {
                "enabled": bool(smoke_results),
                "judged": len(smoke_judged),
                "passed": len(smoke_passed),
            },
        }
    return spread


def _mean_stdev(values: list[float | int]) -> dict[str, float]:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return {"mean": mean, "stdev": 0.0}
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return {"mean": mean, "stdev": math.sqrt(variance)}


def _has_first_shot_token_measurement(result: EvalResult) -> bool:
    return result.total_tokens > 0 or "token_summary" in result.run_config


def is_execution_judged(smoke: Any) -> bool:
    """Single source of truth for the execution-smoke judged set.

    A run is judged only when smoke ran and produced an app-level verdict:
    applicable and not a checker/infra error.
    """
    return bool(smoke is not None and smoke.applicable and smoke.failure_type != "checker_error")

def stability_by_case(results: list[EvalResult]) -> dict[str, dict[str, Any]]:
    """Return per-case pass counts across repeated runs."""
    stability = {}
    for case_id, case_results in results_by_case(results).items():
        passed = sum(1 for r in case_results if r.passed)
        total = len(case_results)
        stability[case_id] = {
            "passed": passed,
            "total": total,
            "label": f"{passed}/{total}",
            "stable": passed == total,
        }
    return stability

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
