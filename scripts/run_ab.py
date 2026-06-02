"""Run two benchmark configurations and generate an A/B diff report."""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from llm_codegen_eval.clients.java_client import JavaServiceClient
from llm_codegen_eval.core.batch_runner import BatchRunAborted, load_cases, run_batch, save_results
from llm_codegen_eval.core.config import EvalRunConfig, java_request_params, load_run_config
from llm_codegen_eval.core.filters import filter_cases_by_id, parse_case_ids
from llm_codegen_eval.core.metrics import (
    TokenSnapshot,
    TokenSummary,
    diff_token_snapshots,
    extract_token_counters,
    fetch_prometheus_metrics,
    summarize_token_delta,
)
from llm_codegen_eval.core.preflight import (
    ChatHistoryCleanupConfig,
    PreflightError,
    clear_chat_history,
)
from llm_codegen_eval.core.result import EvalResult
from llm_codegen_eval.core.reporter import generate_ab_report, save_report

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
    run_label = f" run {run_idx}" if run_idx > 1 else ""
    if phase == "start":
        print(f"[{idx+1}/{total}] {case_id}{run_label}: running...", flush=True)
    elif phase == "done":
        status = "✅" if result.passed else ("⚠️ ERROR" if result.error else "❌")
        print(
            f"[{idx+1}/{total}] {case_id}{run_label}: {status} "
            f"score={result.score}/100 "
            f"duration={result.generation_duration_ms/1000:.1f}s",
            flush=True,
        )
    elif phase == "retry":
        print(
            f"[{idx+1}/{total}] {case_id}{run_label}: infra error, "
            f"retrying ({attempt_idx}/{max_attempts - 1})...",
            flush=True,
        )


async def run_config(
    config: EvalRunConfig,
    cases,
    app_id: str | None,
    runs_per_case: int,
    clear_history: bool,
    mysql_db: str,
    mysql_user: str,
    mysql_password: str | None,
    mysql_host: str,
    mysql_port: int,
    infra_retries: int,
    max_consecutive_infra_failures: int,
    capture_token_metrics: bool,
) -> tuple[list[EvalResult], TokenSummary | None]:
    client = JavaServiceClient(app_id=app_id) if app_id else JavaServiceClient()
    java_params = java_request_params(config)

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

    if clear_history:
        print(f"\nPre-flight ({config.name}): checking chat_history cleanup for appId={client.app_id}...")
        cleanup_chat_history()
        print(f"Pre-flight ({config.name}): mysql cleanup check passed.")

    token_before = None
    if capture_token_metrics:
        token_before = await capture_token_snapshot(client, config.name, "before")

    print(f"\nRunning config {config.name} (agent={config.generation.agent}, java_params={java_params or '-'})")
    print("-" * 70)

    results = await run_batch(
        cases,
        client,
        concurrency=1,
        on_progress=progress_callback,
        runs_per_case=runs_per_case,
        before_run=before_case_run,
        agent=config.generation.agent,
        java_params=java_params,
        infra_retries=infra_retries,
        max_consecutive_infra_failures=max_consecutive_infra_failures,
    )
    token_summary = await capture_token_delta(client, config.name, token_before)
    return results, token_summary


async def capture_token_snapshot(
    client: JavaServiceClient,
    config_name: str,
    phase: str,
) -> TokenSnapshot | None:
    try:
        text = await fetch_prometheus_metrics(client.base_url)
    except Exception as exc:
        print(f"⚠️ Token metrics ({config_name} {phase}) unavailable: {exc}")
        return None
    snapshot = extract_token_counters(text, app_id=client.app_id)
    print(f"Token metrics ({config_name} {phase}): captured {len(snapshot)} counters for appId={client.app_id}.")
    return snapshot


async def capture_token_delta(
    client: JavaServiceClient,
    config_name: str,
    token_before,
) -> TokenSummary | None:
    if token_before is None:
        return None
    token_after = await capture_token_snapshot(client, config_name, "after")
    if token_after is None:
        return None
    summary = summarize_token_delta(diff_token_snapshots(token_before, token_after))
    print(
        f"Token metrics ({config_name} delta): "
        f"input={summary['input']:,}, output={summary['output']:,}, total={summary['total']:,}."
    )
    return summary


async def main(
    config_a_path: Path,
    config_b_path: Path,
    filter_type: str | None = None,
    case_id: str | None = None,
    limit: int | None = None,
    runs_per_case: int = 3,
    clear_history: bool = True,
    app_id: str | None = None,
    mysql_db: str = "ling_ai_code_generation",
    mysql_user: str = "root",
    mysql_password: str | None = None,
    mysql_host: str = "localhost",
    mysql_port: int = 3306,
    infra_retries: int = 1,
    max_consecutive_infra_failures: int = 3,
    capture_token_metrics: bool = True,
):
    if runs_per_case < 1:
        raise ValueError("--runs-per-case must be >= 1")
    if infra_retries < 0:
        raise ValueError("--infra-retries must be >= 0")
    if max_consecutive_infra_failures < 0:
        raise ValueError("--max-consecutive-infra-failures must be >= 0")

    config_a = load_run_config(config_a_path)
    config_b = load_run_config(config_b_path)

    cases = load_cases(CASES_PATH)
    if filter_type:
        cases = [c for c in cases if c.code_type.value == filter_type]
    selected_case_ids = parse_case_ids(case_id)
    if selected_case_ids:
        cases = filter_cases_by_id(cases, selected_case_ids)
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        print("No cases to run.")
        return

    print("=" * 70)
    print("LLM Codegen Eval — A/B Run")
    print(f"A: {config_a.name} (agent={config_a.generation.agent})")
    print(f"B: {config_b.name} (agent={config_b.generation.agent})")
    if selected_case_ids:
        print(f"Selected cases: {', '.join(selected_case_ids)}")
    print(f"Cases: {len(cases)} × {runs_per_case} runs × 2 configs")
    print("=" * 70)

    start = datetime.now()
    results_a: list[EvalResult] = []
    results_b: list[EvalResult] = []
    token_summary_a = None
    token_summary_b = None
    aborted_reason = None
    try:
        results_a, token_summary_a = await run_config(
            config_a,
            cases,
            app_id,
            runs_per_case,
            clear_history,
            mysql_db,
            mysql_user,
            mysql_password,
            mysql_host,
            mysql_port,
            infra_retries,
            max_consecutive_infra_failures,
            capture_token_metrics,
        )
        results_b, token_summary_b = await run_config(
            config_b,
            cases,
            app_id,
            runs_per_case,
            clear_history,
            mysql_db,
            mysql_user,
            mysql_password,
            mysql_host,
            mysql_port,
            infra_retries,
            max_consecutive_infra_failures,
            capture_token_metrics,
        )
    except PreflightError as e:
        print(f"❌ Pre-flight failed: {e}")
        raise
    except BatchRunAborted as e:
        aborted_reason = str(e)
        if not results_a:
            results_a = e.results
        else:
            results_b = e.results
        print(f"\n❌ {aborted_reason}")
        print("Partial raw results and report will be saved for diagnosis.")

    duration = (datetime.now() - start).total_seconds()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_a_path = Path(f"reports/raw_ab_{config_a.name}_{timestamp}.json")
    raw_b_path = Path(f"reports/raw_ab_{config_b.name}_{timestamp}.json")
    save_results(results_a, raw_a_path)
    save_results(results_b, raw_b_path)

    report = generate_ab_report(
        results_a,
        results_b,
        cases,
        config_a.name,
        config_b.name,
        config_details={
            "Duration": f"{duration:.1f}s",
            "Runs per case": str(runs_per_case),
            "Chat history cleared": str(clear_history),
            "Infra retries": str(infra_retries),
            "Max consecutive infra failures": str(max_consecutive_infra_failures),
            "Batch aborted": aborted_reason or "False",
            "Run validity": (
                "invalid for model-quality comparison"
                if aborted_reason else "valid unless report warnings indicate otherwise"
            ),
            "Token metrics": (
                "Prometheus counter deltas by sequential config run"
                if capture_token_metrics else "disabled"
            ),
            "Config A java_service": config_a.java_service or "-",
            "Config B java_service": config_b.java_service or "-",
            "Raw A": str(raw_a_path),
            "Raw B": str(raw_b_path),
        },
        token_summary_a=token_summary_a,
        token_summary_b=token_summary_b,
    )
    report_path = save_report(report, filename_prefix=f"ab_{config_a.name}_vs_{config_b.name}")

    print("-" * 70)
    print(f"A raw results saved to: {raw_a_path}")
    print(f"B raw results saved to: {raw_b_path}")
    print(f"A/B report saved to: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run A/B benchmark comparison")
    parser.add_argument("--config-a", type=Path, required=True, help="YAML config for variant A")
    parser.add_argument("--config-b", type=Path, required=True, help="YAML config for variant B")
    parser.add_argument("--type", choices=["html", "multi_file", "vue_project"], help="Filter by code type")
    parser.add_argument("--case-id", help="Comma-separated case ids to run, e.g. multi_018,multi_019")
    parser.add_argument("--limit", type=int, help="Limit number of cases")
    parser.add_argument("--runs-per-case", type=int, default=3, help="Independent generations per case")
    parser.add_argument("--infra-retries", type=int, default=1,
                        help="Retries for transient provider/network errors per case run")
    parser.add_argument("--max-consecutive-infra-failures", type=int, default=3,
                        help="Abort a sequential batch after this many consecutive infra failures (0 disables)")
    parser.add_argument("--app-id", help="Java service appId to use")
    parser.add_argument("--clear-chat-history", dest="clear_history", action="store_true",
                        default=True, help="Clear chat_history before each case run (default)")
    parser.add_argument("--no-clear-chat-history", dest="clear_history", action="store_false",
                        help="Skip chat_history cleanup")
    parser.add_argument("--mysql-db", default="ling_ai_code_generation")
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument("--mysql-password", help="Falls back to EVAL_MYSQL_PASSWORD or MYSQL_PWD")
    parser.add_argument("--mysql-host", default="localhost")
    parser.add_argument("--mysql-port", type=int, default=3306)
    parser.add_argument("--capture-token-metrics", dest="capture_token_metrics", action="store_true",
                        default=True, help="Capture Java Prometheus token counter deltas (default)")
    parser.add_argument("--no-capture-token-metrics", dest="capture_token_metrics", action="store_false",
                        help="Skip Prometheus token metric capture")
    args = parser.parse_args()

    asyncio.run(main(
        config_a_path=args.config_a,
        config_b_path=args.config_b,
        filter_type=args.type,
        case_id=args.case_id,
        limit=args.limit,
        runs_per_case=args.runs_per_case,
        clear_history=args.clear_history,
        app_id=args.app_id,
        mysql_db=args.mysql_db,
        mysql_user=args.mysql_user,
        mysql_password=args.mysql_password,
        mysql_host=args.mysql_host,
        mysql_port=args.mysql_port,
        infra_retries=args.infra_retries,
        max_consecutive_infra_failures=args.max_consecutive_infra_failures,
        capture_token_metrics=args.capture_token_metrics,
    ))
