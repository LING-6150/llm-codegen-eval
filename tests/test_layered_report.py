import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from llm_codegen_eval.cli import main
from llm_codegen_eval.core.layered_report import build_layer_report, layer_states, markdown_layer_report, requested_checks_failed
from llm_codegen_eval.core.result import EvalResult, ExecutionSmokeResult, BehaviorResult, BehaviorCheck
from llm_codegen_eval.core.results_io import save_results, load_results
from llm_codegen_eval.behavior.suite import SUITE_ROOT


def result(**kwargs):
    defaults = dict(case_id="test", passed=True, score=100, required_passed=1, required_total=1,
                    optional_passed=0, optional_total=0)
    defaults.update(kwargs)
    return EvalResult(**defaults)


def metadata():
    return dict(run_id="test-run", source_kind="artifact-replay", suite="html-behavior-v1", workload_hash="workload", checker_hash="checker")


def smoke(passed=True, failure_type="none"):
    return ExecutionSmokeResult(applicable=True, passed=passed, failure_type=failure_type)


def test_layers_do_not_merge_scores_and_exclude_unjudged_attempts():
    rows = [result(execution_smoke=smoke(), behavior_result=BehaviorResult(status="failed")),
            result(execution_smoke=smoke(), behavior_result=BehaviorResult(status="passed")),
            result(execution_smoke=smoke(False, "checker_error"), behavior_result=BehaviorResult(status="not_run")),
            result(passed=False, score=0, error="Generation failed: ReadTimeout", run_config={"behavior_enabled": True})]
    report = build_layer_report(rows, metadata())
    assert report["summary"]["structural"]["passed"] == 3
    assert report["summary"]["structural"]["not_run"] == 1
    assert report["summary"]["structural"]["pass_rate"] == 1
    assert report["summary"]["behavior"]["judged"] == 2
    assert report["summary"]["behavior"]["pass_rate"] == .5
    assert report["summary"]["behavior"]["not_run"] == 2
    assert report["summary"]["smoke"]["checker_error"] == 1
    assert report["generation_errors"] == 1
    assert rows[0].passed and rows[0].score == 100
    assert requested_checks_failed(rows[0])


def test_smoke_app_failure_leaves_behavior_not_run():
    row = result(execution_smoke=smoke(False, "console_error"), behavior_result=BehaviorResult(status="not_run"))
    assert layer_states(row) == {"structural": "passed", "smoke": "failed", "behavior": "not_run"}


def test_legacy_raws_keep_structural_meaning_and_unavailable_is_not_zero():
    row = result()
    assert layer_states(row) == {"structural": "passed", "smoke": "not_run", "behavior": "not_applicable"}
    report = build_layer_report([row], metadata())
    assert report["summary"]["behavior"]["pass_rate"] is None
    assert build_layer_report([], metadata())["summary"]["structural"]["pass_rate"] is None


def test_markdown_contains_exact_failed_checkpoint_and_evidence():
    row = result(execution_smoke=smoke(), behavior_result=BehaviorResult(status="failed", checks=[
        BehaviorCheck(check_id="pause-preserves-time", status="failed", detail="Expected 2 | got 0 <script>")]),
        browser_evidence={"screenshot": "evidence/test r1/final.png"}, generated_artifact_path="artifacts/test.html")
    md = markdown_layer_report(build_layer_report([row], metadata()))
    assert "pause-preserves-time" in md
    assert "not a live model benchmark" in md
    assert "evidence/test%20r1/final.png" in md
    assert "<script>" not in md and "&lt;script&gt;" in md


def test_behavior_schema_round_trips_without_reinterpreting_passed(tmp_path):
    original = result(behavior_result=BehaviorResult(status="failed"), browser_evidence={"trace": "evidence/trace.zip"})
    save_results([original], tmp_path / "results.json")
    restored = load_results(tmp_path / "results.json")[0]
    assert restored.passed and restored.score == 100
    assert restored.behavior_result.status == "failed"
    assert restored.browser_evidence == original.browser_evidence


def test_evidence_capture_errors_are_visible_and_fail_cli():
    row = result(browser_diagnostics={"evidence_errors": ["Trace: OSError"]})
    assert requested_checks_failed(row)
    assert "evidence capture error" in markdown_layer_report(build_layer_report([row], metadata()))


def test_cli_can_explicitly_disable_behavior_without_claiming_it_passed(tmp_path):
    response = CliRunner().invoke(main, ["run", "--target", "artifacts", "--suite", "html-behavior-v1",
        "--artifacts-dir", str(SUITE_ROOT / "fixtures"), "--case-id", "behavior_notes", "--no-behavior", "--output-dir", str(tmp_path)])
    assert response.exit_code == 0, response.output
    report = json.loads(next(tmp_path.glob("*/layers.json")).read_text())
    assert report["summary"]["behavior"]["not_run"] == 1
    assert report["summary"]["behavior"]["passed"] == 0
    assert report["summary"]["smoke"]["not_run"] == 1


@pytest.mark.browser
@pytest.mark.parametrize("broken", [False, True])
def test_real_cli_keeps_three_verdicts_and_clickable_evidence_separate(tmp_path, broken):
    source = tmp_path / "input"; source.mkdir()
    filename = "behavior_timer--ignores-pause.html" if broken else "behavior_timer.html"
    (source / "behavior_timer.html").write_text((SUITE_ROOT / "fixtures" / filename).read_text())
    output = tmp_path / "reports"
    response = CliRunner().invoke(main, ["run", "--target", "artifacts", "--suite", "html-behavior-v1",
        "--artifacts-dir", str(source), "--case-id", "behavior_timer", "--output-dir", str(output)])
    assert response.exit_code == (1 if broken else 0), response.output
    destination = next(output.iterdir())
    report = json.loads((destination / "layers.json").read_text())
    assert report["summary"]["structural"]["passed"] == 1
    assert report["summary"]["smoke"]["passed"] == 1
    assert report["summary"]["behavior"]["failed" if broken else "passed"] == 1
    row = json.loads((destination / "results.json").read_text())[0]
    assert row["passed"] and row["score"] == 100
    for relative in row["browser_evidence"].values():
        assert (destination / relative).is_file()
    assert row["run_config"]["artifact_sha256"]
    assert json.loads((destination / "run.json").read_text())["checker_hash"]
    if broken:
        assert "pause-preserves-time" in (destination / "report.md").read_text()


def test_cli_reports_browser_environment_fault_without_model_failure(tmp_path, monkeypatch):
    from llm_codegen_eval import cli
    from llm_codegen_eval.behavior.models import BrowserOutcome
    async def missing_browser(*args):
        return BrowserOutcome(smoke(False, "checker_error"), BehaviorResult(status="not_run", detail="Browser unavailable"))
    monkeypatch.setattr(cli, "evaluate_browser", missing_browser)
    response = CliRunner().invoke(main, ["run", "--target", "artifacts", "--suite", "html-behavior-v1",
        "--artifacts-dir", str(SUITE_ROOT / "fixtures"), "--case-id", "behavior_notes", "--output-dir", str(tmp_path)])
    assert response.exit_code == 1
    report = json.loads(next(tmp_path.glob("*/layers.json")).read_text())
    assert report["summary"]["smoke"]["checker_error"] == 1
    assert report["summary"]["behavior"]["failed"] == 0
    assert report["summary"]["behavior"]["pass_rate"] is None


def test_demo_uses_packaged_references_without_live_generation(tmp_path, monkeypatch):
    from llm_codegen_eval import cli
    from llm_codegen_eval.behavior.models import BrowserOutcome
    async def fake_browser(*args):
        return BrowserOutcome(smoke(), BehaviorResult(status="passed"))
    monkeypatch.setattr(cli, "evaluate_browser", fake_browser)
    response = CliRunner().invoke(main, ["demo", "--output-dir", str(tmp_path)])
    assert response.exit_code == 0, response.output
    assert "Hand-written checker references" in response.output
    report = json.loads(next(tmp_path.glob("*/layers.json")).read_text())
    assert report["source_kind"] == "artifact-replay" and report["attempts"] == 5
