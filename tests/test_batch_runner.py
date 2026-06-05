import pytest

from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase
from llm_codegen_eval.core.result import EvalResult
from llm_codegen_eval.core import batch_runner


class FakeClient:
    def __init__(self, healthy: bool = True):
        self.healthy = healthy

    async def login(self):
        return None

    async def health(self):
        return self.healthy


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
    assert final_results[0].run_config["infra_retries_used"] == 1


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
    assert final_results[0].run_config["infra_retries_used"] == 0


@pytest.mark.asyncio
async def test_run_batch_aborts_after_consecutive_infra_failures(monkeypatch):
    async def fake_run_case(case, client, agent=True, java_params=None):
        return make_result("Infra error: empty response from Java service")

    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    with pytest.raises(batch_runner.BatchRunAborted) as exc_info:
        await batch_runner.run_batch(
            [make_case(), make_case(), make_case(), make_case()],
            FakeClient(),
            infra_retries=0,
            max_consecutive_infra_failures=3,
        )

    assert "3 consecutive infra failures" in str(exc_info.value)
    assert len(exc_info.value.results) == 3


@pytest.mark.asyncio
async def test_run_batch_aborts_when_health_precheck_fails():
    with pytest.raises(batch_runner.BatchRunAborted) as exc_info:
        await batch_runner.run_batch(
            [make_case()],
            FakeClient(healthy=False),
        )

    assert "health check failed before run" in str(exc_info.value)
    assert exc_info.value.results == []


@pytest.mark.asyncio
async def test_run_batch_aborts_after_infra_error_when_health_is_down(monkeypatch):
    async def fake_run_case(case, client, agent=True, java_params=None):
        client.healthy = False
        return make_result("Infra error: empty response from Java service")

    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    with pytest.raises(batch_runner.BatchRunAborted) as exc_info:
        await batch_runner.run_batch(
            [make_case(), make_case()],
            FakeClient(),
            infra_retries=0,
        )

    assert "health check failed after infra error" in str(exc_info.value)
    assert len(exc_info.value.results) == 1


@pytest.mark.asyncio
async def test_run_batch_does_not_retry_when_health_is_down(monkeypatch):
    calls = []

    async def fake_run_case(case, client, agent=True, java_params=None):
        calls.append(case.case_id)
        client.healthy = False
        return make_result("Workflow error: Remote host terminated the handshake")

    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    with pytest.raises(batch_runner.BatchRunAborted) as exc_info:
        await batch_runner.run_batch(
            [make_case()],
            FakeClient(),
            infra_retries=1,
        )

    assert len(calls) == 1
    assert "health check failed after infra error" in str(exc_info.value)
    assert len(exc_info.value.results) == 1


@pytest.mark.asyncio
async def test_run_batch_health_check_can_be_disabled(monkeypatch):
    calls = []

    async def fake_run_case(case, client, agent=True, java_params=None):
        calls.append(case.case_id)
        return make_result(None, passed=True)

    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(healthy=False),
        health_check=False,
    )

    assert len(calls) == 1
    assert results[0].passed is True


@pytest.mark.asyncio
async def test_run_batch_applies_cooldown_between_sequential_jobs(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_run_case(case, client, agent=True, java_params=None):
        return make_result(None, passed=True)

    monkeypatch.setattr(batch_runner.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    await batch_runner.run_batch(
        [make_case(), make_case(), make_case()],
        FakeClient(),
        cooldown_seconds=2.5,
    )

    assert sleeps == [2.5, 2.5]


@pytest.mark.asyncio
async def test_run_batch_applies_cooldown_before_infra_retry(monkeypatch):
    sleeps = []
    results = [
        make_result("Workflow error: Remote host terminated the handshake"),
        make_result(None, passed=True),
    ]

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_run_case(case, client, agent=True, java_params=None):
        return results.pop(0)

    monkeypatch.setattr(batch_runner.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        infra_retries=1,
        cooldown_seconds=3,
    )

    assert sleeps == [3]
