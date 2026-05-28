import pytest

from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase
from llm_codegen_eval.core.result import EvalResult
from llm_codegen_eval.core import batch_runner


class FakeClient:
    async def login(self):
        return None


def make_case() -> EvalCase:
    return EvalCase(
        case_id="case_a",
        prompt="Create a page",
        code_type=CodeType.HTML,
        difficulty=Difficulty.EASY,
        required_checks=[],
    )


def make_result(error: str | None, passed: bool = False) -> EvalResult:
    return EvalResult(
        case_id="case_a",
        passed=passed,
        score=100 if passed else 0,
        required_passed=1 if passed else 0,
        required_total=1,
        optional_passed=0,
        optional_total=0,
        error=error,
    )


@pytest.mark.asyncio
async def test_run_batch_retries_transient_infra_error(monkeypatch):
    calls = []
    results = [
        make_result("Workflow error: Remote host terminated the handshake"),
        make_result(None, passed=True),
    ]

    async def fake_run_case(case, client, agent=True, java_params=None):
        calls.append(case.case_id)
        return results.pop(0)

    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    final_results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        infra_retries=1,
    )

    assert len(calls) == 2
    assert final_results[0].passed is True
    assert final_results[0].run_config["infra_retries"] == 1


@pytest.mark.asyncio
async def test_run_batch_does_not_retry_non_infra_failure(monkeypatch):
    calls = []

    async def fake_run_case(case, client, agent=True, java_params=None):
        calls.append(case.case_id)
        return make_result(None, passed=False)

    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    final_results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        infra_retries=1,
    )

    assert len(calls) == 1
    assert final_results[0].passed is False
