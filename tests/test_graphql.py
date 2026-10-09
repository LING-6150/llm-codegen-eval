import json
from pathlib import Path
import pytest
pytest.importorskip("strawberry")
from fastapi.testclient import TestClient
from llm_codegen_eval.api.app import create_app
from llm_codegen_eval.api.store import ResultStore
from llm_codegen_eval.core.result import EvalResult
from llm_codegen_eval.core.results_io import save_results

TOKEN = "test-token-0123456789"

@pytest.fixture
def client(tmp_path):
    rows = [EvalResult(case_id="good", passed=True, score=100, required_passed=1, required_total=1,
                       optional_passed=0, optional_total=0),
            EvalResult(case_id="bad", passed=False, score=0, required_passed=0, required_total=1,
                       optional_passed=0, optional_total=0, error="Generation failed")]
    save_results(rows, tmp_path/"raw_legacy.json")
    save_results(rows, tmp_path/"serving"/"run-1"/"results.json")
    (tmp_path/"serving"/"run-1"/"benchmark.json").write_text(json.dumps({
        "model": "fixture", "label": "demo", "summary": {"latency_p95_ms": 123.0}}))
    return TestClient(create_app(tmp_path, TOKEN))


def query(client, text):
    return client.post("/graphql", json={"query": text}, headers={"Authorization": f"Bearer {TOKEN}"})


def test_auth_and_health(client):
    assert client.get("/healthz").status_code == 200
    assert client.post("/graphql", json={"query": "{runs {runId}}"}).status_code == 401
    assert client.post("/graphql", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_serving_and_legacy_queries(client):
    data = query(client, '{runs(limit: 2) {runId model errors structuralPassRate latencyP95Ms}}').json()
    assert "errors" not in data
    assert len(data["data"]["runs"]) == 2
    serving = next(r for r in data["data"]["runs"] if r["runId"] == "run-1")
    assert serving["model"] == "fixture" and serving["errors"] == 1
    assert serving["structuralPassRate"] == .5 and serving["latencyP95Ms"] == 123
    data = query(client, '{run(runId: "run-1") {results(passed: false, limit: 1) {caseId error}}}').json()
    assert data["data"]["run"]["results"][0]["caseId"] == "bad"
    assert query(client, '{run(runId: "missing") {runId}}').json()["data"]["run"] is None

@pytest.mark.parametrize("query_text", ['{runs(limit: 101) {runId}}', '{runs(offset: -1) {runId}}',
                                       '{run(runId: "../../secret") {runId}}'])
def test_invalid_arguments(client, query_text):
    assert query(client, query_text).json().get("errors")


def test_symlink_escape_and_corrupt_report(tmp_path):
    (tmp_path/"raw_escape.json").symlink_to("/etc/hosts")
    with pytest.raises(ValueError, match="Invalid report path"):
        ResultStore(tmp_path).load("raw_escape")
    (tmp_path/"raw_bad.json").write_text('[{}]')
    with pytest.raises(ValueError, match="Invalid result"):
        ResultStore(tmp_path).load("raw_bad")


def test_mutation_and_alias_limits(client):
    assert query(client, 'mutation {deleteRun(runId: "run-1")}').json().get("errors")
    many = "{" + " ".join(f'a{i}: run(runId: "missing") {{runId}}' for i in range(25)) + "}"
    assert query(client, many).json().get("errors")
