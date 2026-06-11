# llm-codegen-eval

Evaluation harness for a Java LLM code-generation service, built to make A/B changes measurable instead of judged by demo screenshots or vibes.

The harness runs benchmark prompts against a local Java service, captures generated code through SSE, evaluates outputs with deterministic structural checks, records raw JSON plus Markdown reports, and attributes tokens with per-run Prometheus counter windows.

## Current Result

The latest citable result is the Redis-isolated context-pruning rerun from 2026-06-09.

| Claim | Status | Scope |
|---|---|---|
| Structural pass@3 preserved at `90.0% -> 90.0%` | Verified | 10 `multi_file` cases x 3 runs, isolated Redis/MySQL memory |
| Total tokens effectively flat/slightly lower: `323,192 -> 317,785` (`-1.7%`) | Directional | Same isolated run; do not headline as a large token saving |
| CodeGen-stage input reduced by about `18%` | Verified within scope | Per-run token attribution; this is the stage pruning directly controls |
| Pre-#24 `+12.3%` token increase | Invalidated | Caused by Redis chat-memory carryover, not pruning |

Full claim audit: [RESULTS.md](RESULTS.md)

Incident write-up: [Redis chat-memory carryover postmortem](docs/redis-memory-carryover-postmortem.md)

## Why This Exists

LLM code-generation demos are easy to over-read. This repo answers a narrower, engineering-focused question:

> When I change the Java codegen system, can I measure what changed, isolate infrastructure failures from model behavior, and avoid trusting contaminated metrics?

The most important finding was not a token percentage. The harness found that an earlier token result was polluted by Redis `MessageWindowChatMemory` carryover on a shared `appId`. Prompt-composition diagnostics showed that most of the CodeGen prompt was carried-over history. That led to a Java product bug fix: `loadChatHistoryToMemory(...)` returned before `chatMemory.clear()` when MySQL history was empty.

## What This Evaluates

- **Java generation service**: a local Spring Boot service on `localhost:8123`.
- **Structural validation pass@k**: deterministic checks for generated HTML/multi-file artifacts, such as tag existence, counts, attributes, text, and regex expectations.
- **A/B configurations**: YAML configs compare Java service behavior, including context pruning on/off.
- **Token attribution**: per-run Prometheus deltas for token, request, and prompt-size metrics.
- **Reliability behavior**: infra retries, Java health checks, suspicious empty-generation detection, and circuit-breaker aborts.

Important boundary: this is **structural-validation pass@k**, not HumanEval-style execution-based functional correctness.

## Architecture

```text
EvalCase JSON
  -> Python batch runner
  -> JavaServiceClient
  -> Java AI service over SSE
  -> generated code/files
  -> deterministic evaluator checks
  -> EvalResult JSON
  -> Markdown reports + token attribution
```

Key modules:

- `src/llm_codegen_eval/benchmarks/cases.json` stores benchmark cases.
- `src/llm_codegen_eval/clients/java_client.py` calls the Java service.
- `src/llm_codegen_eval/core/batch_runner.py` runs cases, retries infra failures, clears eval memory, and captures per-run metrics.
- `src/llm_codegen_eval/core/token_analysis.py` performs offline per-case token attribution.
- `src/llm_codegen_eval/core/reporter.py` generates benchmark and A/B Markdown reports.
- `scripts/run_benchmark.py` runs one configuration.
- `scripts/run_ab.py` compares two configurations.
- `scripts/analyze_token_attribution.py` analyzes saved raw A/B results.

## Measurement Integrity Story

The context-pruning experiment originally appeared to increase tokens. Instead of shipping that number, the harness added deeper instrumentation:

1. Per-run token attribution localized the increase to CodeGen input.
2. Mechanism metrics showed the model was receiving a much larger prompt.
3. Prompt-composition diagnostics showed the prompt bulk was Redis chat memory, not the current CodeGen input.
4. The Java service bug was traced to `loadChatHistoryToMemory(...)`: when MySQL history was empty, it returned before clearing Redis-backed memory.
5. Eval preflight was hardened to clear both MySQL `chat_history` and Redis chat memory before every run.
6. The contaminated token result was invalidated and the benchmark was rerun under isolated conditions.

Corrected result: context pruning preserved structural pass@3 at 90%, reduced the CodeGen input it directly controls by about 18%, and did not increase total tokens under isolated conditions.

## Engineering Hardening

- **Health gate**: aborts a shard if Java actuator health is not `UP`.
- **Infra retry classification**: provider/network/TLS failures are treated as infrastructure errors, not model-quality failures.
- **Circuit breaker**: stops a run after repeated infra failures instead of filling the report with invalid empty generations.
- **Suspicious empty-generation detection**: flags near-zero-duration empty outputs.
- **Redis/MySQL memory isolation**: clears both persistence surfaces before each case run.
- **Per-run token attribution**: captures Prometheus counter deltas around each attempt, including retry accounting and counter-reset guards.
- **Mechanism attribution**: records CodeGen requests, prompt chars/request, and input tokens/request.

## Prerequisites

- Python `>=3.13`
- `uv`
- Java AI service running locally on `localhost:8123`
- MySQL access to the Java service database for `chat_history` cleanup
- Java diagnostics endpoint enabled for Redis memory cleanup
- Prometheus metrics exposed by the Java service for token attribution

Install Python dependencies:

```bash
uv sync
```

## Quick Start

Run the smallest local smoke test:

```bash
uv run python scripts/test_one_case.py
```

Run a limited benchmark:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_benchmark.py \
  --name smoke \
  --type multi_file \
  --limit 2 \
  --runs-per-case 1 \
  --infra-retries 1
```

By default, benchmark commands:

- use the Java agent workflow configured by the service;
- clear MySQL `chat_history` before each case run;
- clear Redis chat memory before each case run;
- read MySQL password from `--mysql-password`, `EVAL_MYSQL_PASSWORD`, or `MYSQL_PWD`;
- save raw results and Markdown reports under `reports/`.

Use `--no-clear-chat-history` or `--no-clear-redis-memory` only when intentionally measuring behavior with existing conversation state.

## Benchmark Commands

Single-config Multi-File run:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_benchmark.py \
  --name multi_file_baseline \
  --type multi_file \
  --runs-per-case 1 \
  --infra-retries 1
```

Pruning A/B smoke run:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --case-id multi_019,multi_020 \
  --runs-per-case 1 \
  --infra-retries 1 \
  --capture-run-tokens
```

Sharded pass@3-style A/B run:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --case-id multi_011,multi_012 \
  --runs-per-case 3 \
  --infra-retries 1 \
  --max-consecutive-infra-failures 3 \
  --cooldown-seconds 10 \
  --capture-run-tokens
```

Run separate shards for the remaining case pairs and merge/analyze the saved raw files.

## Token Attribution

Per-run attribution is opt-in via `--capture-run-tokens`.

The runner captures one Prometheus scrape before and after each sequential attempt, scoped to the Java `appId`, and writes:

- `EvalResult.total_tokens`
- `run_config["token_summary"]`
- `run_config["mechanism_summary"]`
- optional `run_config["retry_token_summaries"]`
- optional `run_config["token_capture_error"]`

Offline analysis:

```bash
uv run python scripts/analyze_token_attribution.py \
  --raw-a reports/raw_ab_pruning_off_isolated_sharded_20260609_215316.json \
  --raw-b reports/raw_ab_pruning_on_isolated_sharded_20260609_215316.json \
  --config-token-total-a 323192 \
  --config-token-total-b 317785
```

Attribution assumptions:

- sequential runs only;
- one dedicated `appId`;
- no unrelated traffic for that `appId`;
- Prometheus counters do not reset during a run window;
- Redis/MySQL memory isolation is enabled unless intentionally testing memory effects.

## Repository Layout

```text
configs/                         A/B run configuration files
docs/                            demo script, issue notes, and postmortems
scripts/run_benchmark.py          single-configuration benchmark runner
scripts/run_ab.py                 two-configuration A/B runner
scripts/analyze_token_attribution.py offline token/mechanism attribution
src/llm_codegen_eval/benchmarks/  benchmark case definitions
src/llm_codegen_eval/clients/     Java service client
src/llm_codegen_eval/core/        config, running, metrics, reporting, results
tests/                            offline unit tests
```

## Limitations And Non-Goals

- Structural checks do not replace execution-based functional correctness.
- Small benchmark slices are directional; do not imply statistical significance.
- Token attribution depends on metrics isolation and the Java service Prometheus counters.
- Live Java/LLM benchmark runs are manual; offline unit tests cover harness logic.
- Vue project quality claims require a live `vue_project` benchmark report.
- This repo does not attempt multi-model leaderboards, LLM-as-judge scoring, or broad benchmark generalization.

## Demo

- [Three-minute interview demo script](docs/demo-script.md)
- [Canonical result audit](RESULTS.md)
- [Redis memory carryover postmortem](docs/redis-memory-carryover-postmortem.md)

## Roadmap

- Add a lightweight build-level or browser-smoke execution check for generated artifacts.
- Keep `RESULTS.md` as the canonical source of benchmark claims.
- Avoid expanding case types until the structural-vs-execution boundary is tightened.
