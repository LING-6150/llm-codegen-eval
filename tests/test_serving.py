import asyncio
import json
import httpx
import pytest
from llm_codegen_eval.clients.openai_client import OpenAIClient
from llm_codegen_eval.serving.benchmark import benchmark, summarize
from llm_codegen_eval.serving.compare import compare
from llm_codegen_eval.core.case import EvalCase, ElementCheck


def stream(content="<h1>Hello</h1>", usage=True, done=True):
    events = [{"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]},
              {"choices": [{"delta": {"content": content}, "finish_reason": None}]},
              {"choices": [{"delta": {}, "finish_reason": "stop"}]}]
    if usage:
        events.append({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 8, "total_tokens": 15}})
    return "".join("data: " + json.dumps(e) + "\n\n" for e in events) + ("data: [DONE]\n\n" if done else "")

@pytest.mark.asyncio
async def test_sse_usage_and_protocol():
    def handler(request):
        body = json.loads(request.content)
        assert body["stream_options"] == {"include_usage": True}
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, text=stream())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await OpenAIClient(http, "http://test/v1", "model", "test-key").generate("hello")
    assert result["code"] == "<h1>Hello</h1>"
    assert result["usage"]["completion_tokens"] == 8
    assert result["ttft_ms"] <= result["duration_ms"]

@pytest.mark.asyncio
@pytest.mark.parametrize("content,done", [("hi", False), ("", True)])
async def test_broken_streams_rejected(content, done):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=stream(content, done=done)))) as http:
        with pytest.raises(RuntimeError):
            await OpenAIClient(http, "http://test/v1", "model").generate("hello")

@pytest.mark.asyncio
async def test_bounded_parallel_generation_reuses_structural_checks():
    class Fake:
        model = "fixture"
        active = peak = calls = 0
        async def generate(self, prompt):
            self.calls += 1; self.active += 1; self.peak = max(self.peak, self.active)
            call = self.calls
            await asyncio.sleep(.001)
            self.active -= 1
            if call == 4:
                raise httpx.ReadTimeout("sensitive response")
            return {"code": "<h1>Hello</h1>", "duration_ms": 1, "ttft_ms": .5, "usage": None}
    case = EvalCase(case_id="test", prompt="hello", code_type="html", required_checks=[
        ElementCheck(type="tag_exists", selector="h1", description="heading")])
    client = Fake()
    results, records, summary = await benchmark(client, [case], concurrency=2, repeats=5, warmup=1)
    assert client.peak == 2 and client.calls == 6
    assert len(results) == 5
    assert summary["errors"] >= 1
    assert summary["output_tokens_per_second"] is None
    assert any(r.passed for r in results)
    assert "sensitive" not in str(records)


def test_summary_includes_failures_in_denominator():
    summary = summarize([{"duration_ms": 100, "ttft_ms": 10, "usage": {"completion_tokens": 20}},
                         {"error": "timeout", "duration_ms": 900}], 2)
    assert summary["requests_per_second"] == .5
    assert summary["output_tokens_per_second"] == 10
    assert summary["latency_p95_ms"] == 100
    assert summary["errors"] == 1


def test_compare_rejects_changed_workloads():
    with pytest.raises(ValueError, match="Workloads differ"):
        compare({"workload_hash": "a"}, {"workload_hash": "b"})


def test_cli_publishes_complete_reports_and_graphql_can_read_them(monkeypatch, tmp_path):
    from llm_codegen_eval.serving.benchmark import main
    from llm_codegen_eval.api.store import ResultStore
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=stream())), **kwargs))
    monkeypatch.setattr("sys.argv", ["benchmark", "--limit", "1", "--repeats", "1", "--warmup", "0",
        "--environment", "offline protocol fixture, not GPU measurement", "--output-dir", str(tmp_path/"serving")])
    main()
    ids = ResultStore(tmp_path).ids()
    assert len(ids) == 1
    metadata, results = ResultStore(tmp_path).load(ids[0])
    assert metadata["summary"]["successful_requests"] == 1
    assert metadata["summary"]["output_tokens"] == 8
    assert metadata["requests"][0]["case_id"] == results[0].case_id
    assert not list((tmp_path/"serving").glob(".pending-*"))
    assert (tmp_path/"serving"/ids[0]/"report.md").exists()
