import pytest

from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase
from llm_codegen_eval.core.metrics import (
    DiagnosticSnapshot,
    PromptCharsMetricKey,
    RequestMetricKey,
    TokenMetricKey,
)
from llm_codegen_eval.core.result import EvalResult, ExecutionSmokeResult, RepairSummary
from llm_codegen_eval.core import batch_runner


class FakeClient:
    def __init__(self, healthy: bool = True):
        self.healthy = healthy
        self.base_url = "http://fake-java"
        self.app_id = "app_1"

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


def make_execution_failure_result() -> EvalResult:
    result = make_result(None, passed=True)
    result.execution_smoke = ExecutionSmokeResult(
        applicable=True,
        passed=False,
        failure_type="console_error",
        detail="boom",
    )
    return result


def make_snapshot(total: int) -> dict:
    key = TokenMetricKey(
        agent_name="CodeGenAgent",
        model_name="deepseek",
        token_type="input",
    )
    return {key: float(total)}


def make_diagnostic_snapshot(
    total: int,
    requests: int = 1,
    prompt_chars: int = 1000,
) -> DiagnosticSnapshot:
    return DiagnosticSnapshot(
        tokens=make_snapshot(total),
        requests={
            RequestMetricKey(
                agent_name="CodeGenAgent",
                model_name="deepseek",
                status="started",
            ): float(requests)
        },
        prompt_chars={
            PromptCharsMetricKey(
                agent_name="CodeGenAgent",
                model_name="deepseek",
            ): float(prompt_chars)
        },
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


@pytest.mark.asyncio
async def test_run_batch_captures_final_attempt_tokens(monkeypatch):
    snapshots = [
        make_diagnostic_snapshot(100, requests=2, prompt_chars=1000),
        make_diagnostic_snapshot(175, requests=5, prompt_chars=2500),
    ]

    async def fake_capture(client):
        assert client.app_id == "app_1"
        return snapshots.pop(0)

    async def fake_run_case(case, client, agent=True, java_params=None):
        return make_result(None, passed=True)

    monkeypatch.setattr(batch_runner, "_capture_diagnostic_snapshot", fake_capture)
    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        capture_run_tokens=True,
    )

    assert results[0].total_tokens == 75
    assert results[0].run_config["token_summary"]["total"] == 75
    assert results[0].run_config["token_summary"]["by_agent"]["CodeGenAgent"]["total"] == 75
    mechanism = results[0].run_config["mechanism_summary"]["by_agent"]["CodeGenAgent"]
    assert mechanism["requests_started"] == 3
    assert mechanism["prompt_chars"] == 1500
    assert mechanism["input_tokens"] == 75
    assert mechanism["mean_prompt_chars_per_request"] == 500


@pytest.mark.asyncio
async def test_capture_diagnostic_snapshot_scopes_by_client_app_id(monkeypatch):
    seen = {}

    async def fake_fetch(base_url):
        seen["base_url"] = base_url
        return "metrics"

    def fake_extract(text, app_id=None):
        seen["text"] = text
        seen["app_id"] = app_id
        return make_diagnostic_snapshot(100)

    monkeypatch.setattr(batch_runner, "fetch_prometheus_metrics", fake_fetch)
    monkeypatch.setattr(batch_runner, "extract_diagnostic_snapshot", fake_extract)

    snapshot = await batch_runner._capture_diagnostic_snapshot(FakeClient())

    assert snapshot == make_diagnostic_snapshot(100)
    assert seen == {
        "base_url": "http://fake-java",
        "text": "metrics",
        "app_id": "app_1",
    }


@pytest.mark.asyncio
async def test_run_batch_retry_tokens_do_not_pollute_final_attempt(monkeypatch):
    snapshots = [
        make_diagnostic_snapshot(100, requests=1, prompt_chars=1000),
        make_diagnostic_snapshot(125, requests=2, prompt_chars=1250),
        make_diagnostic_snapshot(200, requests=10, prompt_chars=5000),
        make_diagnostic_snapshot(260, requests=11, prompt_chars=5600),
    ]
    generated = [
        make_result("Workflow error: Remote host terminated the handshake"),
        make_result(None, passed=True),
    ]

    async def fake_capture(client):
        return snapshots.pop(0)

    async def fake_run_case(case, client, agent=True, java_params=None):
        return generated.pop(0)

    monkeypatch.setattr(batch_runner, "_capture_diagnostic_snapshot", fake_capture)
    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        infra_retries=1,
        capture_run_tokens=True,
    )

    assert results[0].total_tokens == 60
    assert results[0].run_config["token_summary"]["total"] == 60
    assert results[0].run_config["retry_token_summaries"][0]["total"] == 25
    assert results[0].run_config["mechanism_summary"]["by_agent"]["CodeGenAgent"]["prompt_chars"] == 600


@pytest.mark.asyncio
async def test_run_batch_captures_final_infra_failure_tokens(monkeypatch):
    snapshots = [
        make_diagnostic_snapshot(100),
        make_diagnostic_snapshot(125),
        make_diagnostic_snapshot(200),
        make_diagnostic_snapshot(240),
    ]
    generated = [
        make_result("Workflow error: Remote host terminated the handshake"),
        make_result("Workflow error: Remote host terminated the handshake"),
    ]

    async def fake_capture(client):
        return snapshots.pop(0)

    async def fake_run_case(case, client, agent=True, java_params=None):
        return generated.pop(0)

    monkeypatch.setattr(batch_runner, "_capture_diagnostic_snapshot", fake_capture)
    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        infra_retries=1,
        capture_run_tokens=True,
    )

    assert results[0].passed is False
    assert results[0].total_tokens == 40
    assert results[0].run_config["token_summary"]["total"] == 40
    assert results[0].run_config["retry_token_summaries"][0]["total"] == 25


@pytest.mark.asyncio
async def test_run_batch_marks_token_capture_error_on_counter_reset(monkeypatch):
    snapshots = [make_diagnostic_snapshot(200), make_diagnostic_snapshot(100)]

    async def fake_capture(client):
        return snapshots.pop(0)

    async def fake_run_case(case, client, agent=True, java_params=None):
        return make_result(None, passed=True)

    monkeypatch.setattr(batch_runner, "_capture_diagnostic_snapshot", fake_capture)
    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        capture_run_tokens=True,
    )

    assert results[0].total_tokens == 0
    assert results[0].run_config["token_capture_error"] == "counter reset/regression"


@pytest.mark.asyncio
async def test_run_batch_token_capture_failure_does_not_fail_case(monkeypatch):
    async def fake_capture(client):
        raise RuntimeError("prometheus unavailable")

    async def fake_run_case(case, client, agent=True, java_params=None):
        return make_result(None, passed=True)

    monkeypatch.setattr(batch_runner, "_capture_diagnostic_snapshot", fake_capture)
    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)

    results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        capture_run_tokens=True,
    )

    assert results[0].passed is True
    assert results[0].total_tokens == 0
    assert results[0].run_config["token_capture_error"] == "prometheus unavailable"


@pytest.mark.asyncio
async def test_run_batch_rejects_run_token_capture_with_concurrency():
    with pytest.raises(ValueError, match="capture_run_tokens requires concurrency=1"):
        await batch_runner.run_batch(
            [make_case()],
            FakeClient(),
            concurrency=2,
            capture_run_tokens=True,
        )


@pytest.mark.asyncio
async def test_run_batch_keeps_repair_tokens_separate_from_first_shot(monkeypatch):
    snapshots = [
        make_diagnostic_snapshot(100),
        make_diagnostic_snapshot(175),
        make_diagnostic_snapshot(200),
        make_diagnostic_snapshot(225),
    ]

    async def fake_capture(client):
        return snapshots.pop(0)

    async def fake_run_case(case, client, agent=True, java_params=None, execution_smoke=False):
        return make_execution_failure_result()

    async def fake_run_repair(first_shot, case, client, agent=True, java_params=None):
        assert first_shot.run_config["token_summary"]["total"] == 75
        return RepairSummary(
            attempted=True,
            succeeded=True,
            trigger_failure_type="console_error",
            reason="repair_succeeded",
        )

    monkeypatch.setattr(batch_runner, "_capture_diagnostic_snapshot", fake_capture)
    monkeypatch.setattr(batch_runner, "run_case", fake_run_case)
    monkeypatch.setattr(batch_runner, "run_repair", fake_run_repair)

    results = await batch_runner.run_batch(
        [make_case()],
        FakeClient(),
        capture_run_tokens=True,
        execution_smoke=True,
        repair_on_execution_fail=True,
    )

    assert results[0].total_tokens == 75
    assert results[0].run_config["token_summary"]["total"] == 75
    assert results[0].repair_summary is not None
    assert results[0].repair_summary.token_summary == {
        "input": 25,
        "output": 0,
        "total": 25,
        "by_agent": {"CodeGenAgent": {"input": 25, "output": 0, "total": 25}},
        "by_model": {"deepseek": {"input": 25, "output": 0, "total": 25}},
    }


@pytest.mark.asyncio
async def test_run_batch_repair_requires_execution_smoke():
    with pytest.raises(ValueError, match="repair_on_execution_fail requires execution_smoke=True"):
        await batch_runner.run_batch(
            [make_case()],
            FakeClient(),
            repair_on_execution_fail=True,
            execution_smoke=False,
        )
