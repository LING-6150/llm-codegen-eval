# Part 3: GraphQL result queries

Read-only API: FastAPI + Strawberry, typed queries for serving and existing Java raw JSON reports.
Bearer authentication, bounded pagination, query depth/alias/token limits and path validation.
The API uses artifacts as its source of truth; it does not generate benchmark data or start evaluations.
Designed for a personal demo collection (10 MiB per report, 10,000 files/rows); use a database/index
before scaling to large multi-user collections. No fine-grained multi-tenant authorization is provided.

## Local

```bash
uv sync --frozen --extra api --dev
export EVAL_API_TOKEN="$(openssl rand -hex 24)"
uv run --extra api python -m llm_codegen_eval.api.app --reports-dir reports
```

From a second terminal with the same EVAL_API_TOKEN value:

```bash
curl http://127.0.0.1:8080/graphql \
  -H "Authorization: Bearer $EVAL_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"{ runs(limit: 5) { runId model label errors structuralPassRate latencyP95Ms ttftP95Ms requestsPerSecond outputTokensPerSecond results(limit: 2) { caseId passed score } } }"}'
```

Query a single run with `run(runId: "<actual-id>")`; filter `results(caseId: "html_001", passed: false)`.
Legacy `reports/raw_*.json` IDs are filename stems, e.g. `raw_baseline_20260609`.
Serving reports live at `reports/serving/<run-id>/{benchmark,results}.json`.
The service starts with an empty list until actual reports exist. Never substitute fabricated scores.

## Azure

Rebuild the image after Part 3, then apply the workloads Terraform root with that new tag.
Create a secret after the namespace exists (token is kept outside Terraform state):

```bash
export EVAL_API_TOKEN="$(openssl rand -hex 24)"
kubectl -n llm-eval create secret generic eval-api-auth --from-literal=token="$EVAL_API_TOKEN"
kubectl -n llm-eval rollout status deployment/eval-api
kubectl -n llm-eval port-forward service/eval-api 8080:8080
```

The Deployment initially waits for `eval-api-auth` until you create it.
Query using the same curl command. Shared reports PVC is mounted read-only in the API;
the benchmark Job mounts it read/write. Use authenticated port-forward for recording.
There is no public ingress or unauthenticated result endpoint.

## Record

Show a completed evaluation run, query only selected fields, filter failed cases,
and compare two run IDs. Show an unauthorized request returning HTTP 401.
Use real run outputs for evaluation claims; offline API tests are protocol demonstrations only.

Reference: [Strawberry FastAPI integration](https://strawberry.rocks/docs/integrations/fastapi).
