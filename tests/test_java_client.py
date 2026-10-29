import pytest

from llm_codegen_eval.clients import java_client
from llm_codegen_eval.clients.java_client import JavaServiceClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeAsyncClient:
    response = FakeResponse(200, {"status": "UP"})
    post_response = FakeResponse(200, {"code": 0, "data": {"redisChatMemoryCleared": True}})
    exc = None
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url):
        if self.exc:
            raise self.exc
        return self.response

    async def post(self, url, **kwargs):
        if self.exc:
            raise self.exc
        self.calls.append((url, kwargs))
        return self.post_response


@pytest.mark.asyncio
async def test_java_service_health_returns_true_when_actuator_is_up(monkeypatch):
    FakeAsyncClient.response = FakeResponse(200, {"status": "UP"})
    FakeAsyncClient.exc = None
    FakeAsyncClient.calls = []
    monkeypatch.setattr(java_client.httpx, "AsyncClient", FakeAsyncClient)

    assert await JavaServiceClient().health() is True


@pytest.mark.asyncio
async def test_java_service_health_returns_false_when_status_is_down(monkeypatch):
    FakeAsyncClient.response = FakeResponse(200, {"status": "DOWN"})
    FakeAsyncClient.exc = None
    FakeAsyncClient.calls = []
    monkeypatch.setattr(java_client.httpx, "AsyncClient", FakeAsyncClient)

    assert await JavaServiceClient().health() is False


@pytest.mark.asyncio
async def test_java_service_health_returns_false_on_connection_error(monkeypatch):
    FakeAsyncClient.response = FakeResponse(200, {"status": "UP"})
    FakeAsyncClient.exc = RuntimeError("connection refused")
    FakeAsyncClient.calls = []
    monkeypatch.setattr(java_client.httpx, "AsyncClient", FakeAsyncClient)

    assert await JavaServiceClient().health() is False


@pytest.mark.asyncio
async def test_clear_chat_memory_calls_diagnostics_endpoint(monkeypatch):
    FakeAsyncClient.post_response = FakeResponse(
        200,
        {"code": 0, "data": {"appId": 123, "redisChatMemoryCleared": True}},
    )
    FakeAsyncClient.exc = None
    FakeAsyncClient.calls = []
    monkeypatch.setattr(java_client.httpx, "AsyncClient", FakeAsyncClient)

    payload = await JavaServiceClient(app_id="123").clear_chat_memory()

    assert payload["code"] == 0
    assert FakeAsyncClient.calls == [
        (
            "http://localhost:8123/api/diagnostics/chat-memory/clear",
            {"params": {"appId": "123"}},
        )
    ]


@pytest.mark.asyncio
async def test_clear_chat_memory_raises_when_java_returns_error(monkeypatch):
    FakeAsyncClient.post_response = FakeResponse(
        200,
        {"code": 40300, "message": "Diagnostics endpoints are disabled"},
    )
    FakeAsyncClient.exc = None
    FakeAsyncClient.calls = []
    monkeypatch.setattr(java_client.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(RuntimeError, match="disabled"):
        await JavaServiceClient(app_id="123").clear_chat_memory()


class FakeStreamResponse:
    def __init__(self, lines):
        self.lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self.lines:
            yield line


def sse(event_type, detail=None):
    import json

    inner = {"type": event_type}
    if detail is not None:
        inner["detail"] = detail
    return "data:" + json.dumps({"d": json.dumps(inner)})


@pytest.mark.asyncio
async def test_generate_records_generated_type_and_verify_events(monkeypatch):
    lines = [
        sse("requirement_done", "type=MULTI_FILE"),
        sse("code_token", "<html>"),
        sse("review_done", "score=88,passed=true"),
        sse("verify_done", "passed=false,failures=1,ms=30,first=page_error: x is not defined"),
        sse("verify_done", "passed=true,ms=25"),
    ]

    class StreamClient(FakeAsyncClient):
        def stream(self, method, url, params=None):
            return FakeStreamResponse(lines)

    monkeypatch.setattr(java_client.httpx, "AsyncClient", StreamClient)
    client = JavaServiceClient(base_url="http://fake")
    client.cookies = {"SESSION": "x"}

    result = await client.generate("timer", extra_params={"executionFeedback": True})

    assert result["code"] == "<html>"
    assert result["code_gen_type"] == "multi_file"
    assert result["review_passed"] is True
    assert result["verify_details"] == [
        "passed=false,failures=1,ms=30,first=page_error: x is not defined",
        "passed=true,ms=25",
    ]
