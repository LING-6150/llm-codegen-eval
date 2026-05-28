import subprocess

import pytest

from llm_codegen_eval.core.preflight import (
    ChatHistoryCleanupConfig,
    PreflightError,
    clear_chat_history,
)


def test_clear_chat_history_builds_mysql_command():
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], returncode=0, stdout="", stderr="")

    config = ChatHistoryCleanupConfig(
        app_id="415591816310689792",
        database="ling_ai_code_generation",
        user="root",
        password="secret",
        host="localhost",
        port=3306,
    )

    assert clear_chat_history(config, runner=fake_runner) == 0

    args, kwargs = calls[0]
    cmd = args[0]
    assert cmd == [
        "mysql",
        "-h",
        "localhost",
        "-P",
        "3306",
        "-u",
        "root",
        "-D",
        "ling_ai_code_generation",
        "-e",
        "DELETE FROM chat_history WHERE appId = 415591816310689792;",
    ]
    assert kwargs["env"]["MYSQL_PWD"] == "secret"
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is False


def test_clear_chat_history_rejects_non_numeric_app_id():
    config = ChatHistoryCleanupConfig(app_id="1; DROP TABLE chat_history")

    with pytest.raises(PreflightError, match="invalid appId"):
        clear_chat_history(config)


def test_clear_chat_history_raises_on_mysql_failure():
    def fake_runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], returncode=1, stdout="", stderr="access denied")

    config = ChatHistoryCleanupConfig(app_id="415591816310689792")

    with pytest.raises(PreflightError, match="access denied"):
        clear_chat_history(config, runner=fake_runner)
