"""CLI entry point for running the benchmark suite."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

from llm_codegen_eval.core.batch_runner import (
    BatchRunAborted,
    run_batch,
    load_cases,
    save_results,
)
from llm_codegen_eval.core.reporter import generate_markdown, save_report
from llm_codegen_eval.core.case import CodeType
from llm_codegen_eval.core.config import java_request_params, load_run_config
from llm_codegen_eval.core.filters import filter_cases_by_id, parse_case_ids
from llm_codegen_eval.core.preflight import (
    ChatHistoryCleanupConfig,
    PreflightError,
    clear_chat_history,
)
from llm_codegen_eval.clients.java_client import JavaServiceClient

CASES_PATH = Path("src/llm_codegen_eval/benchmarks/cases.json")

def progress_callback(
    idx,
    total,
    case_id,
    phase,
    result=None,
    run_idx: int = 1,
    attempt_idx: int | None = None,
    max_attempts: int | None = None,
):
    """Print progress to stdout."""
    run_label = f" run {run_idx}" if run_idx > 1 else ""
    if phase == "start":
        print(f"[{idx+1}/{total}] {case_id}{run_label}: running...", flush=True)
    elif phase == "done":
        status = "✅" if result.passed else ("⚠️ ERROR" if result.error else "❌")
        print(
            f"[{idx+1}/{total}] {case_id}{run_label}: {status} "
            f"score={result.score}/100 "
            f"duration={result.generation_duration_ms/1000:.1f}s",
            flush=True
        )
    elif phase == "retry":
        print(
            f"[{idx+1}/{total}] {case_id}{run_label}: infra error, "
            f"retrying ({attempt_idx}/{max_attempts - 1})...",
            flush=True
        )

async def main(
    config_name: str = "baseline",
    filter_type: str | None = None,
    case_id: str | None = None,
    limit: int | None = None,
    clear_history: bool = True,
    app_id: str | None = None,
    mysql_db: str = "ling_ai_code_generation",
    mysql_user: str = "root",
    mysql_password: str | None = None,
    mysql_host: str = "localhost",
    mysql_port: int = 3306,
    runs_per_case: int = 3,
    agent: bool = True,
    config_path: Path | None = None,
    infra_retries: int = 1,
    max_consecutive_infra_failures: int = 3,
    cooldown_seconds: float = 0,
    health_check: bool = True,
    capture_run_tokens: bool = False,
):
    config_metadata = {}
    java_params = {}
    if config_path:
        run_config = load_run_config(config_path)
        config_name = run_config.name
        agent = run_config.generation.agent
        java_params = java_request_params(run_config)
        config_metadata = run_config.metadata

    print("=" * 70)
    print(f"LLM Codegen Eval — Batch Run")
    print(f"Config: {config_name}")
    print(f"Agent workflow: {agent}")
    print(f"Java params: {java_params or '-'}")
    print("=" * 70)

    if runs_per_case < 1:
        raise ValueError("--runs-per-case must be >= 1")
    if infra_retries < 0:
        raise ValueError("--infra-retries must be >= 0")
    if max_consecutive_infra_failures < 0:
        raise ValueError("--max-consecutive-infra-failures must be >= 0")
    if cooldown_seconds < 0:
        raise ValueError("--cooldown-seconds must be >= 0")

    # Load cases
    cases = load_cases(CASES_PATH)
    print(f"\nLoaded {len(cases)} cases from {CASES_PATH}")

    # Optional filtering
    if filter_type:
        cases = [c for c in cases if c.code_type.value == filter_type]
        print(f"Filtered to {len(cases)} {filter_type} cases")

    selected_case_ids = parse_case_ids(case_id)
    if selected_case_ids:
        cases = filter_cases_by_id(cases, selected_case_ids)
        print(f"Filtered to selected cases: {', '.join(selected_case_ids)}")

    if limit is not None:
        cases = cases[:limit]
        print(f"Limited to first {len(cases)} cases")

    if not cases:
        print("No cases to run.")
        return

    client = JavaServiceClient(app_id=app_id) if app_id else JavaServiceClient()

    def cleanup_chat_history():
        clear_chat_history(
            ChatHistoryCleanupConfig(
                app_id=client.app_id,
                database=mysql_db,
                user=mysql_user,
                password=mysql_password,
                host=mysql_host,
                port=mysql_port,
            )
        )

    def before_case_run(case, run_index: int, total_runs: int):
        if clear_history:
            cleanup_chat_history()

    # Pre-flight cleanup
    if clear_history:
        print(f"\nPre-flight: chat_history will be cleared before each case run for appId={client.app_id}.")
        try:
            cleanup_chat_history()
        except PreflightError as e:
            print(f"❌ Pre-flight failed: {e}")
            raise
        print("Pre-flight: mysql cleanup check passed.")
    else:
        print("\nPre-flight: chat_history cleanup skipped.")

    # Run batch
    total_runs = len(cases) * runs_per_case
    print(f"\nRunning {len(cases)} cases × {runs_per_case} runs ({total_runs} total runs, sequential)...")
    print("-" * 70)

    start = datetime.now()

    aborted_reason = None
    try:
        results = await run_batch(
            cases,
            client,
            concurrency=1,
            on_progress=progress_callback,
            runs_per_case=runs_per_case,
            before_run=before_case_run,
            agent=agent,
            java_params=java_params,
            infra_retries=infra_retries,
            max_consecutive_infra_failures=max_consecutive_infra_failures,
            cooldown_seconds=cooldown_seconds,
            health_check=health_check,
            capture_run_tokens=capture_run_tokens,
        )
    except BatchRunAborted as e:
        results = e.results
        aborted_reason = str(e)
        print(f"\n❌ {aborted_reason}")
        print("Partial raw results and report will be saved for diagnosis.")
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
            "Runs per case": str(runs_per_case),
            "App ID": client.app_id,
            "Chat history cleared": str(clear_history),
            "Agent workflow": str(agent),
            "Java params": java_params or "-",
            "Infra retries": str(infra_retries),
            "Max consecutive infra failures": str(max_consecutive_infra_failures),
            "Cooldown seconds": str(cooldown_seconds),
            "Health check": str(health_check),
            "Run token attribution": str(capture_run_tokens),
            "Run token attribution mode": (
                "Prometheus per-attempt counter delta; valid only for sequential runs "
                "with no concurrent traffic on the same appId"
                if capture_run_tokens else "disabled"
            ),
            "Batch aborted": aborted_reason or "False",
            "Run validity": (
                "invalid for model-quality comparison"
                if aborted_reason else "valid unless report warnings indicate otherwise"
            ),
            **{f"Metadata: {k}": v for k, v in config_metadata.items()},
        }
    )

    report_path = save_report(report, filename_prefix=config_name)
    print(f"Report saved to: {report_path}")

    # Print summary to console
    from llm_codegen_eval.core.stats import compute_summary
    summary = compute_summary(results)
    from llm_codegen_eval.core.stats import pass_at_k
    pass_k = pass_at_k(results, runs_per_case)
    pass_1 = pass_at_k(results, 1)
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if runs_per_case > 1:
        print(f"pass@{runs_per_case}:     {pass_k.get('pass_rate', 0):.1%} ({pass_k['passed_cases']}/{pass_k['total_cases']} cases)")
        print(f"pass@1:     {pass_1.get('pass_rate', 0):.1%} ({pass_1['passed_cases']}/{pass_1['total_cases']} cases)")
        print(f"Run pass:   {summary.get('pass_rate', 0):.1%} ({summary['passed']}/{summary['total']} runs)")
    else:
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
    parser.add_argument("--config", type=Path,
                       help="YAML config file defining name and generation settings")
    parser.add_argument("--type", choices=["html", "multi_file", "vue_project"],
                       help="Filter by code type")
    parser.add_argument("--case-id", help="Comma-separated case ids to run, e.g. multi_018,multi_019")
    parser.add_argument("--limit", type=int, help="Limit number of cases (for testing)")
    parser.add_argument("--runs-per-case", type=int, default=3,
                       help="Number of independent generations per case for pass@k")
    parser.add_argument("--infra-retries", type=int, default=1,
                        help="Retries for transient provider/network errors per case run")
    parser.add_argument("--max-consecutive-infra-failures", type=int, default=3,
                        help="Abort a sequential batch after this many consecutive infra failures (0 disables)")
    parser.add_argument("--cooldown-seconds", type=float, default=0,
                        help="Sleep between sequential runs and before infra retries")
    parser.add_argument("--health-check", dest="health_check", action="store_true",
                        default=True, help="Abort when Java actuator health is not UP (default)")
    parser.add_argument("--no-health-check", dest="health_check", action="store_false",
                        help="Disable Java actuator health gate")
    parser.add_argument("--capture-run-tokens", dest="capture_run_tokens", action="store_true",
                        default=False, help="Capture per-run Prometheus token deltas")
    parser.add_argument("--no-capture-run-tokens", dest="capture_run_tokens", action="store_false",
                        help="Disable per-run token attribution (default)")
    parser.add_argument("--agent", dest="agent", action="store_true",
                       default=True, help="Use Java Multi-Agent workflow (default)")
    parser.add_argument("--no-agent", dest="agent", action="store_false",
                       help="Use single-agent generation")
    parser.add_argument("--app-id", help="Java service appId to use for this run")
    parser.add_argument("--clear-chat-history", dest="clear_history", action="store_true",
                       default=True, help="Clear chat_history for appId before running (default)")
    parser.add_argument("--no-clear-chat-history", dest="clear_history", action="store_false",
                       help="Skip chat_history cleanup")
    parser.add_argument("--mysql-db", default="ling_ai_code_generation",
                       help="MySQL database containing chat_history")
    parser.add_argument("--mysql-user", default="root", help="MySQL user")
    parser.add_argument("--mysql-password",
                       help="MySQL password; falls back to EVAL_MYSQL_PASSWORD or MYSQL_PWD")
    parser.add_argument("--mysql-host", default="localhost", help="MySQL host")
    parser.add_argument("--mysql-port", type=int, default=3306, help="MySQL port")
    args = parser.parse_args()

    asyncio.run(main(
        config_name=args.name,
        filter_type=args.type,
        case_id=args.case_id,
        limit=args.limit,
        clear_history=args.clear_history,
        app_id=args.app_id,
        mysql_db=args.mysql_db,
        mysql_user=args.mysql_user,
        mysql_password=args.mysql_password,
        mysql_host=args.mysql_host,
        mysql_port=args.mysql_port,
        runs_per_case=args.runs_per_case,
        agent=args.agent,
        config_path=args.config,
        infra_retries=args.infra_retries,
        max_consecutive_infra_failures=args.max_consecutive_infra_failures,
        cooldown_seconds=args.cooldown_seconds,
        health_check=args.health_check,
        capture_run_tokens=args.capture_run_tokens,
    ))
