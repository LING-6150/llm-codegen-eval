"""CLI entry point for running the benchmark suite."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

from llm_codegen_eval.core.batch_runner import (
    run_batch,
    load_cases,
    save_results,
)
from llm_codegen_eval.core.reporter import generate_markdown, save_report
from llm_codegen_eval.core.case import CodeType
from llm_codegen_eval.clients.java_client import JavaServiceClient

CASES_PATH = Path("src/llm_codegen_eval/benchmarks/cases.json")

def progress_callback(idx, total, case_id, phase, result=None):
    """Print progress to stdout."""
    if phase == "start":
        print(f"[{idx+1}/{total}] {case_id}: running...", flush=True)
    elif phase == "done":
        status = "✅" if result.passed else ("⚠️ ERROR" if result.error else "❌")
        print(
            f"[{idx+1}/{total}] {case_id}: {status} "
            f"score={result.score}/100 "
            f"duration={result.generation_duration_ms/1000:.1f}s",
            flush=True
        )

async def main(
    config_name: str = "baseline",
    filter_type: str | None = None,
    limit: int | None = None
):
    print("=" * 70)
    print(f"LLM Codegen Eval — Batch Run")
    print(f"Config: {config_name}")
    print("=" * 70)

    # Load cases
    cases = load_cases(CASES_PATH)
    print(f"\nLoaded {len(cases)} cases from {CASES_PATH}")

    # Optional filtering
    if filter_type:
        cases = [c for c in cases if c.code_type.value == filter_type]
        print(f"Filtered to {len(cases)} {filter_type} cases")

    if limit:
        cases = cases[:limit]
        print(f"Limited to first {len(cases)} cases")

    if not cases:
        print("No cases to run.")
        return

    # Run batch
    print(f"\nRunning {len(cases)} cases (sequential, this may take a while)...")
    print("-" * 70)

    client = JavaServiceClient()
    start = datetime.now()

    try:
        results = await run_batch(
            cases,
            client,
            concurrency=1,
            on_progress=progress_callback
        )
    except Exception as e:
        print(f"\n❌ Batch run failed: {e}")
        raise

    duration = (datetime.now() - start).total_seconds()
    print("-" * 70)
    print(f"\nCompleted in {duration:.1f}s ({duration/60:.1f} min)")

    # Save raw results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = Path(f"reports/raw_{config_name}_{timestamp}.json")
    save_results(results, raw_path)
    print(f"Raw results saved to: {raw_path}")

    # Generate report
    print("\nGenerating report...")
    report = generate_markdown(
        results,
        cases,
        config_name=config_name,
        config_details={
            "Duration": f"{duration:.1f}s",
            "Cases": str(len(cases)),
        }
    )

    report_path = save_report(report, filename_prefix=config_name)
    print(f"Report saved to: {report_path}")

    # Print summary to console
    from llm_codegen_eval.core.stats import compute_summary
    summary = compute_summary(results)
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"pass@1:     {summary.get('pass_rate', 0):.1%} ({summary['passed']}/{summary['total']})")
    print(f"Avg score:  {summary.get('avg_score', 0):.1f}/100")
    print(f"Avg duration: {summary.get('avg_duration_ms', 0)/1000:.1f}s")
    if summary.get("avg_review_score") is not None:
        print(f"Avg review: {summary['avg_review_score']:.1f}/100")

if __name__ == "__main__":
    # Simple arg parsing
    import argparse
    parser = argparse.ArgumentParser(description="Run LLM codegen eval benchmark")
    parser.add_argument("--name", default="baseline", help="Run config name")
    parser.add_argument("--type", choices=["html", "multi_file", "vue_project"],
                       help="Filter by code type")
    parser.add_argument("--limit", type=int, help="Limit number of cases (for testing)")
    args = parser.parse_args()

    asyncio.run(main(
        config_name=args.name,
        filter_type=args.type,
        limit=args.limit
    ))
