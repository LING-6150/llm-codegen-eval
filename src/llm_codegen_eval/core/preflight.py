"""Pre-flight checks and cleanup for benchmark runs."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ChatHistoryCleanupConfig:
    app_id: str
    database: str = "ling_ai_code_generation"
    user: str = "root"
    password: str | None = None
    host: str = "localhost"
    port: int = 3306
    mysql_bin: str = "mysql"
    timeout_seconds: int = 10


class PreflightError(RuntimeError):
    """Raised when a pre-flight cleanup step fails."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def clear_chat_history(
    config: ChatHistoryCleanupConfig,
    runner: Runner = subprocess.run,
) -> int:
    """Delete chat_history rows for one appId before a benchmark run.

    Returns the mysql process return code. The app_id is constrained to digits
    because it is interpolated into the SQL statement.
    """

    if not config.app_id.isdigit():
        raise PreflightError(f"Refusing to clear chat_history for invalid appId: {config.app_id!r}")

    sql = f"DELETE FROM chat_history WHERE appId = {config.app_id};"
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

    env = os.environ.copy()
    password = config.password if config.password is not None else os.environ.get("EVAL_MYSQL_PASSWORD")
    if password:
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
