import asyncio
import json
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from llm_codegen_eval import cli
from llm_codegen_eval.core.case import EvalCase, ElementCheck
from llm_codegen_eval.generators import ArtifactGenerator


@pytest.fixture
def case(monkeypatch):
    case = EvalCase(case_id="sample", prompt="Return a heading", code_type="html",
        required_checks=[ElementCheck(type="tag_exists", selector="h1", description="Heading")])
    monkeypatch.setattr(cli, "suite_cases", lambda _: [case])
    return case


def test_help_and_case_listing_without_services():
    result = CliRunner().invoke(cli.main, ["--help"])
    assert result.exit_code == 0 and "run" in result.output and "list-cases" in result.output
    result = CliRunner().invoke(cli.main, ["list-cases"])
    assert result.exit_code == 0 and "html_001" in result.output


def test_saved_artifacts_run_without_http_and_keep_full_sidecars(case, tmp_path, monkeypatch):
    source = tmp_path / "input"; source.mkdir()
    code = "<h1>Hello</h1>" + " " * 3000
    (source / "sample.html").write_text(code)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: pytest.fail("Offline replay called HTTP"))
    output = tmp_path / "runs"
    response = CliRunner().invoke(cli.main, ["run", "--target", "artifacts", "--artifacts-dir", str(source),
        "--repeats", "2", "--output-dir", str(output)])
    assert response.exit_code == 0, response.output
    run = next(output.iterdir())
    assert not run.name.startswith(".pending")
    rows = json.loads((run / "results.json").read_text())
    assert len(rows) == 2 and rows[0]["generated_code_truncated"]
    assert (run / rows[0]["generated_artifact_path"]).read_text() == code
    assert json.loads((run / "run.json").read_text())["source_kind"] == "artifact-replay"
    assert "not a live model benchmark" in (run / "report.md").read_text()


def test_openai_target_stream_is_evaluated_and_key_is_not_saved(case, tmp_path, monkeypatch):
    def respond(request):
        body = json.loads(request.content)
        assert body["model"] == "provider/model"
        assert request.headers["authorization"] == "Bearer private-test-key"
        assert body["messages"][-1]["content"] == case.prompt
        events = [{"choices": [{"delta": {"content": "<h1>API</h1>"}, "finish_reason": None}]},
                  {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                  {"choices": [], "usage": {"total_tokens": 9}}]
        return httpx.Response(200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events) + "data: [DONE]\n\n")
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setenv("INFERENCE_API_KEY", "private-test-key")
    result = CliRunner().invoke(cli.main, ["run", "--target", "openai:provider/model", "--base-url", "http://test/v1", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    run = next(tmp_path.iterdir())
    row = json.loads((run / "results.json").read_text())[0]
    assert row["passed"] and row["total_tokens"] == 9
    assert "private-test-key" not in "".join(p.read_text() for p in run.rglob("*") if p.is_file())


@pytest.mark.parametrize("args", [
    ["--target", "artifacts"], ["--target", "openai:"], ["--target", "unknown"],
    ["--target", "openai:m", "--case-id", "../../outside"],
    ["--target", "openai:m", "--base-url", "https://user:secret@test/v1"],
    ["--target", "openai:m", "--limit", "0"],
])
def test_configuration_errors_fail_before_output(args, tmp_path):
    result = CliRunner().invoke(cli.main, ["run", *args, "--output-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert not list(tmp_path.iterdir())


def test_missing_artifact_is_a_generation_error_with_exit_one(case, tmp_path):
    source = tmp_path / "source"; source.mkdir()
    output = tmp_path / "runs"
    response = CliRunner().invoke(cli.main, ["run", "--target", "artifacts", "--artifacts-dir", str(source), "--output-dir", str(output)])
    assert response.exit_code == 1
    row = json.loads(next(output.glob("*/results.json")).read_text())[0]
    assert row["error"] == "Generation failed: FileNotFoundError"
    assert row["generated_artifact_path"] is None


@pytest.mark.asyncio
async def test_artifact_adapter_blocks_symlink_escape(case, tmp_path):
    source = tmp_path / "source"; source.mkdir()
    outside = tmp_path / "outside.html"; outside.write_text("<h1>Secret</h1>")
    (source / "sample.html").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        await ArtifactGenerator(source).generate(case)


@pytest.mark.asyncio
async def test_timeout_error_does_not_expose_exception_text(case, tmp_path):
    class Slow:
        async def generate(self, _):
            await asyncio.sleep(1)
    rows = await cli.evaluate_cases(Slow(), [case], 1, tmp_path, .01, False, {})
    assert rows[0].error == "Generation failed: TimeoutError"
