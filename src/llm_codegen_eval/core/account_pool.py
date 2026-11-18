"""Schedule independent Java app benchmarks on a single host."""

import asyncio
import hashlib
import json
import multiprocessing
import os
import sqlite3
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from contextlib import closing, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from .cases_io import load_cases
from .config import java_request_params, load_run_config, validate_batch_options
from .filters import select_cases
from .preflight import resolve_app_id
from .reporter import new_report_id


@dataclass(frozen=True)
class Account:
    app_id: str
    account: str | None
    password_env: str


def read_accounts(path: Path) -> dict[str, Account]:
    accounts = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or row.keys() - {"app_id", "account", "password_env"}:
                    raise ValueError("expected app_id and optional account and password_env")
                if not all(isinstance(value, str) and value.strip() for value in row.values()):
                    raise ValueError("manifest fields must be nonempty strings")
                app_id = resolve_app_id(row["app_id"])
                if app_id in accounts:
                    raise ValueError(f"duplicate app ID {app_id}")
                account = row.get("account") or os.getenv("EVAL_JAVA_ACCOUNT")
                secret = row.get("password_env", "EVAL_JAVA_PASSWORD")
                accounts[app_id] = Account(app_id, account, secret)
            except (KeyError, ValueError, RuntimeError) as exc:
                raise ValueError(f"Accounts manifest line {line_number}: {exc}") from exc
    if not accounts:
        raise ValueError("Accounts manifest is empty")
    return accounts


def host_capacity():
    import psutil

    cpus = os.process_cpu_count() or 1
    process = psutil.Process()
    if hasattr(process, "cpu_affinity"):
        cpus = min(cpus, len(process.cpu_affinity()) or cpus)
    available = psutil.virtual_memory().available
    membership = Path("/proc/self/cgroup")
    if sys.platform == "linux" and membership.is_file():
        # Affinity can expose more CPUs than the cgroup quota. Limits can also
        # be inherited from an ancestor, including the container's mount root.
        root = Path("/sys/fs/cgroup")
        for line in membership.read_text().splitlines():
            if not line.startswith("0::"):
                continue
            group = (root / line[3:].lstrip("/")).resolve()
            if not group.is_relative_to(root):
                group = root
            for level in (group, *group.parents):
                if not level.is_relative_to(root):
                    continue
                cpu = level / "cpu.max"
                if cpu.is_file():
                    quota, period = cpu.read_text().split()
                    if quota != "max":
                        cpus = min(cpus, max(1, int(quota) // int(period)))
                memory = level / "memory.max"
                if memory.is_file() and (limit := memory.read_text().strip()) != "max":
                    usage = int((level / "memory.current").read_text())
                    available = min(available, max(0, int(limit) - usage))
    return cpus, available // (1024 * 1024)


def worker_plan(count, requested, browser):
    cpus, memory_mib = host_capacity()
    budget = 768 if browser else 256
    workers = min(count, cpus, max(1, memory_mib * 3 // (4 * budget)), requested or 8)
    if os.name == "nt":
        workers = min(workers, 61)
    return {"accounts": count, "usable_cpus": cpus, "available_mib": memory_mib,
            "estimated_mib_per_worker": budget, "workers": workers}


def add_account_options(parser):
    parser.add_argument("--accounts", type=Path, help="JSONL manifest for independent Java app IDs")
    parser.add_argument("--workers", type=int, help="Cap parallel account workers (automatic cap: 8)")
    parser.add_argument("--plan", action="store_true", help="Print host capacity and exit before contacting Java")
    parser.add_argument("--batch-dir", type=Path, help="New directory for per-account reports and progress")
    parser.add_argument("--resume", action="store_true", help="Retry unfinished accounts in --batch-dir")


def _run_account(main, options, account, root):
    directory = root / account.app_id
    directory.mkdir(exist_ok=True)
    with (directory / "worker.log").open("a", encoding="utf-8") as log, redirect_stdout(log):
        try:
            asyncio.run(main(**options, app_id=account.app_id, java_account=account.account,
                             password_env=account.password_env, output_dir=directory))
        except SystemExit as exc:
            print(f"Benchmark exited: {exc.code}")
            return False
        except Exception as exc:
            print(f"Benchmark failed: {type(exc).__name__}: {exc}")
            return False
    # Only publish completion once both raw and Markdown reports are closed.
    marker = directory / "completed.tmp"
    marker.write_text("completed\n", encoding="utf-8")
    marker.replace(directory / "completed")
    return True


def _schedule(main, options, remaining, root, workers):
    count = len(remaining)
    remaining = iter(remaining)
    failed = 0
    finished = 0
    with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        pending = {}
        while True:
            while len(pending) < workers and (account := next(remaining, None)) is not None:
                pending[pool.submit(_run_account, main, options, account, root)] = account.app_id
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                app_id = pending.pop(future)
                if not future.result():
                    failed += 1
                    print(f"App {app_id} failed. See {root / app_id / 'worker.log'}", flush=True)
                finished += 1
                if finished % 100 == 0:
                    print(f"Processed {finished}/{count} scheduled accounts ({failed} failed).", flush=True)
    return failed


def run_java_command(main, args, cases_path, **options):
    if args.accounts is None:
        if args.workers is not None or args.plan or args.resume or args.batch_dir:
            raise SystemExit("Account pool options require --accounts.")
        return asyncio.run(main(**options))
    if args.app_id is not None or (args.workers is not None and args.workers < 1):
        raise SystemExit("Use distinct IDs from --accounts and a positive worker count.")
    if args.resume and args.batch_dir is None:
        raise SystemExit("--resume requires --batch-dir")
    try:
        validate_batch_options(args.runs_per_case, args.infra_retries, args.max_consecutive_infra_failures,
                               args.cooldown_seconds, args.execution_smoke, args.repair_on_execution_fail)
        selected = select_cases(load_cases(cases_path), args.type, args.case_id, args.limit)
        if not selected or (args.limit is not None and args.limit < 1):
            raise ValueError("Select at least one benchmark case.")
        for key in ("config_path", "config_a_path", "config_b_path"):
            if path := options.get(key):
                java_request_params(load_run_config(path))
        accounts = read_accounts(args.accounts)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    plan = worker_plan(len(accounts), args.workers, options["execution_smoke"])
    arms = 2 if "config_b_path" in options else 1
    plan["planned_first_shots"] = len(accounts) * len(selected) * args.runs_per_case * arms
    print(json.dumps(plan), flush=True)
    if args.plan:
        return
    root = args.batch_dir or Path("reports") / "account-runs" / new_report_id()
    if args.resume and not (root / "workload.json").is_file():
        raise SystemExit("No saved workload in the requested resume directory")
    # Compare settings and input contents before accepting completion markers.
    del options["app_id"]
    settings = {k: v for k, v in options.items() if k != "mysql_password"}
    for key, value in settings.items():
        if isinstance(value, Path):
            settings[key] = hashlib.sha256(value.read_bytes()).hexdigest()
    runner = Path(main.__code__.co_filename)
    code = hashlib.sha256(runner.read_bytes())
    package = Path(__file__).resolve().parents[1]
    for source in sorted(package.rglob("*.py")):
        code.update(source.relative_to(package).as_posix().encode())
        code.update(hashlib.sha256(source.read_bytes()).digest())
    workload = {"command": runner.name, "settings": settings, "harness_sha256": code.hexdigest(),
                "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
                "accounts_sha256": hashlib.sha256(args.accounts.read_bytes()).hexdigest(),
                "default_account": os.getenv("EVAL_JAVA_ACCOUNT"),
                "java_url": os.getenv("EVAL_JAVA_BASE_URL")}
    if not args.resume:
        root.mkdir(parents=True, exist_ok=False)
    print(f"Account run directory: {root}", flush=True)
    with closing(sqlite3.connect(root / "coordinator.sqlite", timeout=0)) as lock:
        try:
            lock.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                raise SystemExit("This batch directory already has an active coordinator.") from exc
            raise
        record = root / "workload.json"
        if args.resume:
            if json.loads(record.read_text(encoding="utf-8")) != workload:
                raise SystemExit("Workload changed. Use a new batch directory.")
        else:
            staging = record.with_suffix(".tmp")
            staging.write_text(json.dumps(workload, indent=2), encoding="utf-8")
            staging.replace(record)
        remaining = [a for a in accounts.values() if not (root / a.app_id / "completed").is_file()]
        for account in remaining:
            if not account.account or not os.getenv(account.password_env):
                raise SystemExit(f"Missing Java credentials for app {account.app_id}.")
        failed = 0
        if remaining:
            failed = _schedule(main, options, remaining, root, min(len(remaining), plan["workers"]))
    print(f"Account run finished: {len(accounts) - failed} completed, {failed} failed.")
    if failed:
        raise SystemExit(1)
