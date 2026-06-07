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
