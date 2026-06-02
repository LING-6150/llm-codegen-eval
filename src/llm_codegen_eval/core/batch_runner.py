"""Batch runner: run multiple eval cases and collect results."""

import asyncio
import json
from pathlib import Path

from .case import EvalCase
from .result import EvalResult
from .runner import run_case
from ..clients.java_client import JavaServiceClient


class BatchRunAborted(RuntimeError):
    """Raised when a batch is stopped after repeated infra failures."""

    def __init__(self, message: str, results: list[EvalResult]):
        super().__init__(message)
        self.results = results


async def run_batch(
    cases: list[EvalCase],
    client: JavaServiceClient,
    concurrency: int = 1,
    on_progress=None,
    runs_per_case: int = 1,
    before_run=None,
    agent: bool = True,
    java_params: dict | None = None,
    infra_retries: int = 0,
    max_consecutive_infra_failures: int = 3,
) -> list[EvalResult]:
    """Run all cases sequentially or with limited concurrency.

    Note: Default concurrency=1 because the Java service is shared state
    and high concurrency may trigger LLM rate limits or unstable behavior.
    """

    # Pre-login once
    await client.login()

    if runs_per_case < 1:
        raise ValueError("runs_per_case must be >= 1")
    if infra_retries < 0:
        raise ValueError("infra_retries must be >= 0")
    if max_consecutive_infra_failures < 0:
        raise ValueError("max_consecutive_infra_failures must be >= 0")

    semaphore = asyncio.Semaphore(concurrency)

    jobs = [
        (case, case_idx, run_idx)
        for case_idx, case in enumerate(cases)
        for run_idx in range(runs_per_case)
    ]

    async def run_with_semaphore(
        case: EvalCase,
        case_idx: int,
        run_idx: int,
        job_idx: int,
    ) -> EvalResult:
        async with semaphore:
            if on_progress:
                on_progress(job_idx, len(jobs), case.case_id, "start", run_idx=run_idx + 1)

            result = None
            for attempt_idx in range(infra_retries + 1):
                if before_run:
                    maybe_awaitable = before_run(case, run_idx + 1, runs_per_case)
                    if asyncio.iscoroutine(maybe_awaitable):
                        await maybe_awaitable

                result = await run_case(case, client, agent=agent, java_params=java_params)
                if not is_infra_error(result) or attempt_idx >= infra_retries:
                    break

                if on_progress:
                    on_progress(
                        job_idx,
                        len(jobs),
                        case.case_id,
                        "retry",
                        result,
                        run_idx=run_idx + 1,
                        attempt_idx=attempt_idx + 1,
                        max_attempts=infra_retries + 1,
                    )

            assert result is not None
            result.run_config.update({
                "run_index": run_idx + 1,
                "runs_per_case": runs_per_case,
                "agent": agent,
                "java_params": java_params or {},
                "infra_retries": infra_retries,
                "infra_retries_used": attempt_idx,
            })

            if on_progress:
                on_progress(job_idx, len(jobs), case.case_id, "done", result, run_idx=run_idx + 1)

            return result

    if concurrency == 1:
        results = []
        consecutive_infra_failures = 0
        for job_idx, (case, case_idx, run_idx) in enumerate(jobs):
            result = await run_with_semaphore(case, case_idx, run_idx, job_idx)
            results.append(result)

            if is_infra_error(result):
                consecutive_infra_failures += 1
            else:
                consecutive_infra_failures = 0

            if (
                max_consecutive_infra_failures > 0
                and consecutive_infra_failures >= max_consecutive_infra_failures
            ):
                raise BatchRunAborted(
                    "Batch aborted after "
                    f"{consecutive_infra_failures} consecutive infra failures",
                    results,
                )
        return results

    tasks = [
        run_with_semaphore(case, case_idx, run_idx, job_idx)
        for job_idx, (case, case_idx, run_idx) in enumerate(jobs)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    return results

def load_cases(cases_path: Path) -> list[EvalCase]:
    """Load EvalCases from a JSON file."""
    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)
    return [EvalCase(**c) for c in data]

def save_results(
    results: list[EvalResult],
    output_path: Path
):
    """Save raw results as JSON for later analysis."""
    output_path.parent.mkdir(exist_ok=True, parents=True)

    serialized = []
    for r in results:
        d = r.model_dump(mode="json")
        # Truncate generated_code in saved JSON to keep file size manageable
        if d.get("generated_code") and len(d["generated_code"]) > 2000:
            d["generated_code"] = d["generated_code"][:2000] + "... [truncated]"
        serialized.append(d)

    output_path.write_text(
        json.dumps(serialized, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )

def load_results(results_path: Path) -> list[EvalResult]:
    """Load raw EvalResult JSON from a previous benchmark run."""
    with open(results_path, encoding="utf-8") as f:
        data = json.load(f)
    return [EvalResult(**r) for r in data]

def is_infra_error(result: EvalResult) -> bool:
    """Return true for transient provider/network errors worth rerunning."""
    if not result.error:
        return False

    error = result.error.lower()
    transient_markers = [
        "remote host terminated",
        "handshake",
        "tls",
        "i/o error",
        "timeout",
        "timed out",
        "429",
        "too many requests",
        "connection reset",
        "connection refused",
        "connection aborted",
        "temporarily unavailable",
        "produced empty code stream",
        "returned empty code stream",
        "empty response from java service",
    ]
    return any(marker in error for marker in transient_markers)
