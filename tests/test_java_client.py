import pytest

from llm_codegen_eval.clients import java_client
from llm_codegen_eval.clients.java_client import JavaServiceClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeAsyncClient:
    response = FakeResponse(200, {"status": "UP"})
    exc = None

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


@pytest.mark.asyncio
async def test_java_service_health_returns_true_when_actuator_is_up(monkeypatch):
    FakeAsyncClient.response = FakeResponse(200, {"status": "UP"})
    FakeAsyncClient.exc = None
    monkeypatch.setattr(java_client.httpx, "AsyncClient", FakeAsyncClient)

    assert await JavaServiceClient().health() is True


@pytest.mark.asyncio
async def test_java_service_health_returns_false_when_status_is_down(monkeypatch):
    FakeAsyncClient.response = FakeResponse(200, {"status": "DOWN"})
    FakeAsyncClient.exc = None
    monkeypatch.setattr(java_client.httpx, "AsyncClient", FakeAsyncClient)

    assert await JavaServiceClient().health() is False


@pytest.mark.asyncio
async def test_java_service_health_returns_false_on_connection_error(monkeypatch):
    FakeAsyncClient.response = FakeResponse(200, {"status": "UP"})
    FakeAsyncClient.exc = RuntimeError("connection refused")
    monkeypatch.setattr(java_client.httpx, "AsyncClient", FakeAsyncClient)

    assert await JavaServiceClient().health() is False
