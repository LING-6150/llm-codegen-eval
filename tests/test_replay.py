import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from llm_codegen_eval.core.case import CodeType, EvalCase
from llm_codegen_eval.core.replay import (
    assert_replayable_generated_code,
    load_replay_artifacts,
    replay_artifacts,
    replay_report_markdown,
)
from llm_codegen_eval.core.result import EvalResult
from llm_codegen_eval.core.results_io import load_results, save_results


def html_005_case() -> EvalCase:
    return EvalCase(
        case_id="html_005",
        prompt="A simple personal portfolio page",
        code_type=CodeType.HTML,
        difficulty="easy",
        required_checks=[
            {"type": "tag_exists", "selector": "h1, h2", "description": "Name or title as heading"},
            {"type": "tag_exists", "selector": "img", "description": "Photo or avatar image"},
            {
                "type": "regex_match",
                "pattern": "(about|bio|introduction|hello|i am|my name)",
                "description": "About/bio section text",
            },
            {
                "type": "regex_match",
                "pattern": "(skills?|projects?|experience|portfolio|work)",
                "description": "Skills or projects section",
            },
        ],
        optional_checks=[],
    )


def make_result(case_id: str = "html_005", generated_code: str = "<h1>Hello</h1>") -> EvalResult:
    return EvalResult(
        case_id=case_id,
        passed=True,
        score=100,
        required_passed=1,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        generated_code=generated_code,
        run_config={"run_index": 1},
    )


def test_report_only_replay_renders_banner_and_metadata_without_live_calls(tmp_path: Path, monkeypatch):
    raw = tmp_path / "raw.json"
    save_results([make_result()], raw)

    def fail_subprocess(*args, **kwargs):
        raise AssertionError("replay must not call subprocess")

    class ForbiddenAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("replay must not create HTTP clients")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    httpx = pytest.importorskip("httpx")
    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenAsyncClient)

    report = replay_report_markdown(raw, [html_005_case()], config_name="replay_test")

    lines = report.splitlines()
    assert lines[0] == "# Eval Report — replay_test"
    assert lines[2] == "REPLAY REPORT - re-rendered from saved raw results, not a live benchmark run."
    assert "**Replay mode**: report-only" in report
    assert "**Live Java calls**: False" in report
    assert "**Provider calls**: False" in report
    forbidden_wording = [
        "functional correctness",
        "new benchmark result",
        "model improved",
        "quality regression",
        "token savings",
    ]
    for phrase in forbidden_wording:
        assert phrase not in report.lower()


def test_results_io_and_replay_import_no_live_modules():
    for module_name in [
        "llm_codegen_eval.core.replay",
        "llm_codegen_eval.core.reporter",
        "llm_codegen_eval.core.results_io",
        "llm_codegen_eval.core.failure_taxonomy",
        "llm_codegen_eval.core.batch_runner",
        "llm_codegen_eval.clients.java_client",
        "llm_codegen_eval.core.metrics",
        "llm_codegen_eval.core.runner",
        "llm_codegen_eval.core.preflight",
        "llm_codegen_eval.evaluators.html_eval",
        "llm_codegen_eval.evaluators.vue_eval",
        "llm_codegen_eval.evaluators.execution_smoke",
        "playwright.async_api",
    ]:
        sys.modules.pop(module_name, None)

    importlib.import_module("llm_codegen_eval.core.results_io")
    importlib.import_module("llm_codegen_eval.core.replay")

    assert "llm_codegen_eval.core.batch_runner" not in sys.modules
    assert "llm_codegen_eval.clients.java_client" not in sys.modules
    assert "llm_codegen_eval.core.metrics" not in sys.modules
    assert "llm_codegen_eval.core.runner" not in sys.modules
    assert "llm_codegen_eval.core.preflight" not in sys.modules
    assert "llm_codegen_eval.evaluators.html_eval" not in sys.modules
    assert "llm_codegen_eval.evaluators.vue_eval" not in sys.modules
    assert "llm_codegen_eval.evaluators.execution_smoke" not in sys.modules
    assert "playwright.async_api" not in sys.modules


def test_save_results_writes_structured_truncation_metadata(tmp_path: Path):
    raw = tmp_path / "raw.json"
    long_code = "x" * 2100
    save_results([make_result(generated_code=long_code)], raw)

    data = json.loads(raw.read_text(encoding="utf-8"))
    assert data[0]["generated_code_truncated"] is True
    assert data[0]["generated_code"].endswith("... [truncated]")

    loaded = load_results(raw)
    assert loaded[0].generated_code_truncated is True


def test_load_results_marks_legacy_truncation_marker(tmp_path: Path):
    raw = tmp_path / "legacy.json"
    payload = make_result(generated_code="x" * 20).model_dump(mode="json")
    payload.pop("generated_code_truncated")
    payload["generated_code"] = "abc... [truncated]"
    raw.write_text(json.dumps([payload]), encoding="utf-8")

    loaded = load_results(raw)

    assert loaded[0].generated_code_truncated is True


def test_truncated_raw_cannot_be_replayed_as_artifact():
    result = make_result(generated_code="abc... [truncated]")
    result.generated_code_truncated = True

    with pytest.raises(ValueError, match="truncated"):
        assert_replayable_generated_code(result)


@pytest.mark.asyncio
async def test_artifact_replay_structurally_evaluates_good_and_bad_fixtures():
    fixtures = load_replay_artifacts(Path("tests/fixtures/replay"))

    results = await replay_artifacts(fixtures, [html_005_case()])
    by_case = {result.generated_code: result for result in results}

    assert len(results) == 2
    assert any(result.passed is True for result in by_case.values())
    assert any(result.passed is False for result in by_case.values())
    assert all(result.run_config["replay_mode"] == "artifact-fixture" for result in results)
    assert all(result.run_config["live_java_calls"] is False for result in results)


@pytest.mark.asyncio
async def test_artifact_replay_can_run_execution_smoke_when_browser_available():
    fixtures = [
        artifact
        for artifact in load_replay_artifacts(Path("tests/fixtures/replay/html_005_good.json"))
    ]

    results = await replay_artifacts(fixtures, [html_005_case()], execution_smoke=True)
    smoke = results[0].execution_smoke
    assert smoke is not None
    if smoke.failure_type == "checker_error" and smoke.detail and (
        "Executable doesn't exist" in smoke.detail
        or "playwright install" in smoke.detail
        or "BrowserType.launch" in smoke.detail
    ):
        pytest.skip(f"Playwright browser is not installed: {smoke.detail.splitlines()[0]}")

    assert smoke.applicable is True
    assert smoke.passed is True
    assert smoke.failure_type == "none"
