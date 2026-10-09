"""Bounded-concurrency inference measurements and existing structural evaluation."""
import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import httpx
from ..clients.openai_client import OpenAIClient, SYSTEM_PROMPT
from ..core.cases_io import load_cases
from ..core.case import CodeType
from ..core.result import EvalResult
from ..core.results_io import save_results
from ..core.runner import _evaluate_generated_code
from ..core.reporter import generate_markdown
from ..evaluators.execution_smoke import evaluate_execution_smoke

CASES = Path(__file__).parents[1] / "benchmarks" / "cases.json"

def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * q) - 1)]

def summarize(records, elapsed):
    ok = [r for r in records if not r.get("error")]
    token_complete = bool(ok) and all(isinstance((r.get("usage") or {}).get("completion_tokens"), int) for r in ok)
    tokens = sum(r["usage"]["completion_tokens"] for r in ok) if token_complete else None
    return {"requests": len(records), "successful_requests": len(ok), "errors": len(records)-len(ok),
            "elapsed_seconds": elapsed, "requests_per_second": len(ok)/elapsed,
            "output_tokens": tokens, "output_tokens_per_second": tokens/elapsed if tokens is not None else None,
            "latency_p50_ms": percentile([r["duration_ms"] for r in ok], .5),
            "latency_p95_ms": percentile([r["duration_ms"] for r in ok], .95),
            "ttft_p50_ms": percentile([r["ttft_ms"] for r in ok if r.get("ttft_ms") is not None], .5),
            "ttft_p95_ms": percentile([r["ttft_ms"] for r in ok if r.get("ttft_ms") is not None], .95),
            "length_limited_requests": sum(r.get("finish_reason") == "length" for r in ok)}

async def benchmark(client, cases, concurrency=1, repeats=1, warmup=1, execution_smoke=False):
    if not cases or concurrency < 1 or repeats < 1 or warmup < 0:
        raise ValueError("Need cases, positive concurrency/repeats, and nonnegative warmup")
    for i in range(warmup):
        await client.generate(cases[i % len(cases)].prompt)
    semaphore = asyncio.Semaphore(concurrency)
    async def request(case, repeat):
        async with semaphore:
            start = perf_counter()
            try:
                record = await client.generate(case.prompt)
            except Exception as exc:
                # No bodies or credentials in stored errors.
                record = {"error": f"Inference failed: {type(exc).__name__}",
                          "duration_ms": (perf_counter()-start)*1000}
            return case, repeat, record
    start = perf_counter()
    generated = await asyncio.gather(*(request(c, i) for i in range(repeats) for c in cases))
    elapsed = perf_counter()-start
    results, records = [], []
    for case, repeat, record in generated:
        if record.get("error"):
            result = EvalResult(case_id=case.case_id, passed=False, score=0,
                                required_passed=0, required_total=len(case.required_checks),
                                optional_passed=0, optional_total=len(case.optional_checks), error=record["error"])
        else:
            result = await _evaluate_generated_code(record["code"], case)
            if execution_smoke:
                result.execution_smoke = await evaluate_execution_smoke(record["code"], case)
        metrics = {k:v for k,v in record.items() if k != "code"}
        result.generation_duration_ms = round(record["duration_ms"])
        result.total_tokens = (record.get("usage") or {}).get("total_tokens", 0)
        result.run_config = {"backend": "openai-compatible", "model": client.model,
                             "repeat": repeat, "inference": metrics}
        results.append(result)
        records.append({"case_id": case.case_id, "repeat": repeat, **metrics})
    summary = summarize(records, elapsed)
    summary["structural_pass_rate"] = sum(r.passed for r in results)/len(results)
    return results, records, summary

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-0.5B-Instruct")
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--label", default="vllm")
    parser.add_argument("--environment", required=True, help="GPU, server version, deployment, cache policy")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/serving"))
    parser.add_argument("--execution-smoke", action="store_true")
    args = parser.parse_args()
    if args.limit < 1 or args.max_tokens < 1 or args.concurrency < 1 or args.repeats < 1 or args.warmup < 0:
        parser.error("limit, max-tokens, concurrency and repeats must be positive; warmup must be nonnegative")
    cases = [c for c in load_cases(args.cases) if c.code_type == CodeType.HTML][:args.limit]
    async def run():
        async with httpx.AsyncClient(timeout=180, limits=httpx.Limits(max_connections=args.concurrency)) as http:
            client = OpenAIClient(http, args.base_url, args.model, os.getenv("INFERENCE_API_KEY", ""),
                                  args.max_tokens, args.temperature, args.seed)
            return await benchmark(client, cases, args.concurrency, args.repeats, args.warmup, args.execution_smoke)
    results, records, summary = asyncio.run(run())
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    destination = args.output_dir / run_id
    destination.mkdir(parents=True, exist_ok=False)
    workload = {"cases": [c.model_dump(mode="json") for c in cases], "repeats": args.repeats,
                "max_tokens": args.max_tokens, "temperature": args.temperature, "seed": args.seed,
                "system_prompt": SYSTEM_PROMPT}
    fingerprint = hashlib.sha256(json.dumps(workload, sort_keys=True).encode()).hexdigest()
    git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    metadata = {"schema_version": 1, "run_id": run_id, "label": args.label, "model": args.model,
                "base_url": args.base_url.split("?")[0], "concurrency": args.concurrency,
                "warmup": args.warmup, "workload_hash": fingerprint, "workload": workload,
                "environment": args.environment, "python": platform.python_version(),
                "git_commit": git.stdout.strip(), "summary": summary, "requests": records}
    save_results(results, destination/"results.json")
    (destination/"benchmark.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (destination/"report.md").write_text(generate_markdown(results, cases, args.label) +
        "\n## Serving measurements\n\n```json\n" + json.dumps(summary, indent=2) + "\n```\n", encoding="utf-8")
    print(destination)
    print(json.dumps(summary, indent=2))
    if summary["errors"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
