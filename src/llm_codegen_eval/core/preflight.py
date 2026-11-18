"""Pre-flight checks and cleanup for benchmark runs."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import tempfile
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ChatHistoryCleanupConfig:
    app_id: str
    database: str = "ling_ai_code_generation"
    user: str = "llm_eval"
    password: str | None = None
    host: str = "localhost"
    port: int = 3306
    mysql_bin: str = "mysql"
    timeout_seconds: int = 10


class PreflightError(RuntimeError):
    """Raised when a pre-flight cleanup step fails."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def resolve_app_id(value: str | None) -> str:
    value = os.environ.get("EVAL_APP_ID") if value is None else value
    if not value:
        raise PreflightError("Set EVAL_APP_ID or --app-id to a provisioned evaluation app ID.")
    if not value.isascii() or not value.isdecimal() or len(value) > 19 or not 0 < int(value) < 2**63:
        raise PreflightError("invalid appId: expected a positive Java long")
    return str(int(value))


@contextmanager
def reserve_app_id(app_id: str):
    """Keep local benchmark processes from sharing one app's memory and counters."""
    app_id = resolve_app_id(app_id)
    directory = Path(tempfile.gettempdir()) / "llm-codegen-eval-locks"
    directory.mkdir(mode=0o700, exist_ok=True)
    with closing(sqlite3.connect(directory / f"{app_id}.sqlite", timeout=0)) as connection:
        try:
            connection.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                raise PreflightError(f"Another local benchmark is using appId={app_id}") from exc
            raise
        yield


def clear_chat_history(
    config: ChatHistoryCleanupConfig,
    runner: Runner = subprocess.run,
) -> int:
    """Delete chat_history rows for one appId before a benchmark run.

    Returns the mysql process return code. The app_id is constrained to digits
    because it is interpolated into the SQL statement.
    """

    sql = f"DELETE FROM chat_history WHERE appId = {resolve_app_id(config.app_id)};"
    cmd = [
        config.mysql_bin,
        "-h",
        config.host,
        "-P",
        str(config.port),
        "-u",
        config.user,
        "-D",
        config.database,
        "-e",
        sql,
    ]

    password = config.password if config.password is not None else os.environ.get("EVAL_MYSQL_PASSWORD")
    env = os.environ.copy()
    if password is not None:
        env["MYSQL_PWD"] = password

    try:
        completed = runner(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PreflightError(
            f"MySQL client not found: {config.mysql_bin!r}. Install mysql CLI or pass --no-clear-chat-history."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PreflightError(
            f"Timed out clearing chat_history for appId={config.app_id} after {config.timeout_seconds}s."
        ) from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise PreflightError(
            f"Failed to clear chat_history for appId={config.app_id}: {stderr or 'mysql exited non-zero'}"
        )

    return completed.returncode
