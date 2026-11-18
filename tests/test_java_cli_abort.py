import json
import importlib
import runpy
import shutil
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from llm_codegen_eval.core.result import EvalResult


@pytest.mark.parametrize(("command", "partial_count"), [
    ("run_benchmark", 0), ("run_benchmark", 1), ("run_ab", 0), ("run_ab", 1),
])
def test_cli_preserves_aborted_run_before_exiting(monkeypatch, tmp_path, command, partial_count):
    batch_runner = importlib.import_module("llm_codegen_eval.core.batch_runner")
    repo = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    case_path = Path("src/llm_codegen_eval/benchmarks/cases.json")
    case_path.parent.mkdir(parents=True)
    shutil.copyfile(repo / case_path, case_path)
    args = [command, "--limit", "2", "--runs-per-case", "1", "--no-clear-chat-history", "--no-clear-redis-memory"]
    if command == "run_ab":
        args += ["--config-a", str(repo / "configs/agent_off.yaml"), "--config-b",
                 str(repo / "configs/agent_on.yaml"), "--no-capture-token-metrics"]
    result = EvalResult(case_id="html_001", passed=False, score=0, required_passed=0, required_total=1,
                        optional_passed=0, optional_total=0, error="timed out")
    abort = batch_runner.BatchRunAborted("fixture abort", [result] * partial_count)
    monkeypatch.setattr(batch_runner, "run_batch", AsyncMock(side_effect=abort))
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exit_status:
        runpy.run_path(str(repo / "scripts" / f"{command}.py"), run_name="__main__")
    assert exit_status.value.code == 1
    report, = Path("reports").glob("*.md")
    content = report.read_text(encoding="utf-8")
    assert "fixture abort" in content and f"{partial_count} / 2" in content
    assert "Winner Summary" not in content
    raw = list(Path("reports").glob("raw_*.json"))
    assert len(raw) == (2 if command == "run_ab" else 1)
    assert sum(len(json.loads(p.read_text(encoding="utf-8"))) for p in raw) == partial_count
