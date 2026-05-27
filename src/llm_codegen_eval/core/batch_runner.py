"""Batch runner: run multiple eval cases and collect results."""

import asyncio
import json
from pathlib import Path
from typing import Optional

from .case import EvalCase
from .result import EvalResult
from .runner import run_case
from ..clients.java_client import JavaServiceClient

async def run_batch(
    cases: list[EvalCase],
    client: JavaServiceClient,
    concurrency: int = 1,
    on_progress=None
) -> list[EvalResult]:
    """Run all cases sequentially or with limited concurrency.

    Note: Default concurrency=1 because the Java service is shared state
    and high concurrency may trigger LLM rate limits or unstable behavior.
    """

    # Pre-login once
    await client.login()

    results: list[EvalResult] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def run_with_semaphore(case: EvalCase, idx: int) -> EvalResult:
        async with semaphore:
            if on_progress:
                on_progress(idx, len(cases), case.case_id, "start")

            result = await run_case(case, client)

            if on_progress:
                on_progress(idx, len(cases), case.case_id, "done", result)

            return result

    tasks = [run_with_semaphore(c, i) for i, c in enumerate(cases)]
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
