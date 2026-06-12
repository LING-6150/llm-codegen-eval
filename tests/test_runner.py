import pytest

from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase, ElementCheck
from llm_codegen_eval.core.result import EvalResult, ExecutionSmokeResult
from llm_codegen_eval.core.runner import run_case, run_repair, should_attempt_repair


class FakeClient:
    def __init__(self):
        self.agent_values = []
        self.extra_params_values = []

    async def generate(self, prompt: str, agent: bool = True, extra_params=None):
        self.agent_values.append(agent)
        self.extra_params_values.append(extra_params)
        return {
            "code": "<html><body><h1>Hello</h1></body></html>",
            "review_score": 90,
            "review_passed": True,
            "duration_ms": 123,
            "error": None,
        }


class RepairClient:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt: str, agent: bool = True, extra_params=None):
        self.prompts.append(prompt)
        return {
            "code": "<html><body><h1>Hello</h1></body></html>",
            "review_score": None,
            "review_passed": None,
            "duration_ms": 50,
            "error": None,
        }


class EmptyResponseClient:
    async def generate(self, prompt: str, agent: bool = True, extra_params=None):
        return {
            "code": "",
            "review_score": None,
            "review_passed": None,
            "duration_ms": 17,
            "error": None,
        }


def make_case() -> EvalCase:
    return EvalCase(
        case_id="html_fake",
        prompt="Create hello page",
        code_type=CodeType.HTML,
        difficulty=Difficulty.EASY,
        required_checks=[
            ElementCheck(type="tag_exists", selector="h1", description="Heading")
        ],
    )


@pytest.mark.asyncio
async def test_run_case_passes_agent_flag_to_client():
    case = make_case()
    client = FakeClient()

    result = await run_case(case, client, agent=False, java_params={"contextPruning": True})

    assert client.agent_values == [False]
    assert client.extra_params_values == [{"contextPruning": True}]
    assert result.passed is True
    assert result.run_config["agent"] is False
    assert result.run_config["java_params"] == {"contextPruning": True}


@pytest.mark.asyncio
async def test_run_case_marks_fast_empty_response_as_infra_error():
    result = await run_case(make_case(), EmptyResponseClient())

    assert result.passed is False
    assert result.score == 0
    assert result.error == "Infra error: empty response from Java service"
    assert result.generation_duration_ms == 17


@pytest.mark.asyncio
async def test_run_case_attaches_execution_smoke_when_enabled(monkeypatch):
    async def fake_execution_smoke(code, case):
        return ExecutionSmokeResult(
            applicable=True,
            passed=True,
            failure_type="none",
            checked_selectors=["h1"],
        )

    monkeypatch.setattr(
        "llm_codegen_eval.core.runner.evaluate_execution_smoke",
        fake_execution_smoke,
    )

    result = await run_case(make_case(), FakeClient(), execution_smoke=True)

    assert result.passed is True
    assert result.execution_smoke is not None
    assert result.execution_smoke.passed is True
    assert result.execution_smoke.checked_selectors == ["h1"]


@pytest.mark.asyncio
async def test_run_case_does_not_call_execution_smoke_when_disabled(monkeypatch):
    async def unexpected_execution_smoke(code, case):
        raise AssertionError("execution smoke should be opt-in")

    monkeypatch.setattr(
        "llm_codegen_eval.core.runner.evaluate_execution_smoke",
        unexpected_execution_smoke,
    )

    result = await run_case(make_case(), FakeClient(), execution_smoke=False)

    assert result.passed is True
    assert result.execution_smoke is None


def test_should_attempt_repair_uses_app_failure_whitelist():
    result = make_result_for_repair(passed=True, failure_type="console_error")

    assert should_attempt_repair(result) is True


def test_should_not_attempt_repair_for_checker_error_or_structural_failure_without_app_failure():
    checker_error = make_result_for_repair(passed=True, failure_type="checker_error")
    structural_failure = make_result_for_repair(passed=False, failure_type="none", smoke_passed=True)

    assert should_attempt_repair(checker_error) is False
    assert should_attempt_repair(structural_failure) is False


def test_should_attempt_repair_for_structural_failure_with_app_execution_failure():
    result = make_result_for_repair(passed=False, failure_type="console_error")

    assert should_attempt_repair(result) is True


def test_should_not_attempt_repair_for_unknown_failure_type():
    result = make_result_for_repair(passed=True, failure_type="new_failure_type")

    assert should_attempt_repair(result) is False


@pytest.mark.asyncio
async def test_run_repair_records_repaired_result_without_overwriting_first_shot(monkeypatch):
    first_shot = make_result_for_repair(passed=True, failure_type="console_error")
    first_shot_score = first_shot.score
    first_shot_smoke = first_shot.execution_smoke

    async def repaired_execution_smoke(code, case):
        return ExecutionSmokeResult(
            applicable=True,
            passed=True,
            failure_type="none",
            checked_selectors=["h1"],
        )

    monkeypatch.setattr(
        "llm_codegen_eval.core.runner.evaluate_execution_smoke",
        repaired_execution_smoke,
    )

    repair = await run_repair(first_shot, make_case(), RepairClient())

    assert repair.attempted is True
    assert repair.succeeded is True
    assert repair.repaired_structural_passed is True
    assert repair.repaired_execution_smoke is not None
    assert repair.repaired_execution_smoke.passed is True
    assert first_shot.score == first_shot_score
    assert first_shot.execution_smoke is first_shot_smoke


def make_result_for_repair(
    passed: bool,
    failure_type: str,
    smoke_passed: bool = False,
):
    return EvalResult(
        case_id="html_fake",
        passed=passed,
        score=100 if passed else 0,
        required_passed=1 if passed else 0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        generated_code="<html><body><h1>Broken</h1></body></html>",
        execution_smoke=ExecutionSmokeResult(
            applicable=True,
            passed=smoke_passed,
            failure_type=failure_type,
            detail="boom",
            checked_selectors=["h1"],
        ),
    )
