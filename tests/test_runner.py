import pytest

from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase, ElementCheck
from llm_codegen_eval.core.result import ExecutionSmokeResult
from llm_codegen_eval.core.runner import run_case


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
