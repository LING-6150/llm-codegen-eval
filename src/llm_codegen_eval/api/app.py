"""Authenticated GraphQL query API over existing evaluation artifacts."""
import argparse
import hmac
import os
from pathlib import Path
import strawberry
from strawberry.extensions import QueryDepthLimiter, MaxAliasesLimiter, MaxTokensLimiter
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI, Depends, Header, HTTPException
from starlette.concurrency import run_in_threadpool
from .store import ResultStore


def pagination(limit, offset):
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
        raise ValueError("limit must be 1..100; offset must be 0..10000")

@strawberry.type
class CaseResult:
    case_id: str
    passed: bool
    score: int
    duration_ms: int
    total_tokens: int
    error: str | None
    smoke_passed: bool | None

@strawberry.type
class Run:
    run_id: str
    model: str | None
    label: str | None
    requests: int
    errors: int
    structural_pass_rate: float | None
    latency_p95_ms: float | None
    ttft_p95_ms: float | None
    requests_per_second: float | None
    output_tokens_per_second: float | None

    @strawberry.field
    async def results(self, info: strawberry.Info, case_id: str | None = None,
                      passed: bool | None = None, limit: int = 20, offset: int = 0) -> list[CaseResult]:
        pagination(limit, offset)
        loaded = await run_in_threadpool(info.context["store"].load, self.run_id)
        if loaded is None:
            return []
        rows = [r for r in loaded[1] if (case_id is None or r.case_id == case_id)
                and (passed is None or r.passed == passed)]
        return [CaseResult(case_id=r.case_id, passed=r.passed, score=r.score,
                           duration_ms=r.generation_duration_ms, total_tokens=r.total_tokens, error=r.error,
                           smoke_passed=r.execution_smoke.passed if r.execution_smoke and r.execution_smoke.applicable else None)
                for r in rows[offset:offset+limit]]

async def get_run(store, run_id):
    loaded = await run_in_threadpool(store.load, run_id)
    if loaded is None:
        return None
    metadata, results = loaded
    summary = metadata.get("summary", {})
    return Run(run_id=run_id, model=metadata.get("model"), label=metadata.get("label"),
               requests=len(results), errors=sum(r.error is not None for r in results),
               structural_pass_rate=sum(r.passed for r in results)/len(results) if results else None,
               latency_p95_ms=summary.get("latency_p95_ms"), ttft_p95_ms=summary.get("ttft_p95_ms"),
               requests_per_second=summary.get("requests_per_second"),
               output_tokens_per_second=summary.get("output_tokens_per_second"))

@strawberry.type
class Query:
    @strawberry.field
    async def runs(self, info: strawberry.Info, limit: int = 20, offset: int = 0) -> list[Run]:
        pagination(limit, offset)
        store = info.context["store"]
        ids = await run_in_threadpool(store.ids)
        rows = [await get_run(store, run_id) for run_id in ids[offset:offset+limit]]
        return [r for r in rows if r is not None]

    @strawberry.field
    async def run(self, info: strawberry.Info, run_id: str) -> Run | None:
        return await get_run(info.context["store"], run_id)

schema = strawberry.Schema(Query, extensions=[lambda: QueryDepthLimiter(max_depth=8),
    lambda: MaxAliasesLimiter(max_alias_count=20), lambda: MaxTokensLimiter(max_token_count=2000)])

def create_app(root: Path, token: str) -> FastAPI:
    if len(token) < 16:
        raise ValueError("EVAL_API_TOKEN must contain at least 16 characters")
    store = ResultStore(root)
    async def authenticate(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(status_code=401, detail="Bearer token required")
    async def context():
        return {"store": store}
    app = FastAPI(title="LLM evaluation results", docs_url=None, redoc_url=None)
    app.include_router(GraphQLRouter(schema, context_getter=context, graphql_ide=None,
                                     allow_queries_via_get=False, subscription_protocols=[]),
                       prefix="/graphql", dependencies=[Depends(authenticate)])
    @app.get("/healthz")
    async def health():
        return {"status": "ok"}
    return app

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.reports_dir, os.getenv("EVAL_API_TOKEN", "")), host=args.host, port=args.port)

if __name__ == "__main__":
    main()
