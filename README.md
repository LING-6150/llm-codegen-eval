# llm-codegen-eval

Production-style evaluation harness for a Java multi-agent code generation system.

The harness runs prompt cases against a local Java AI service, captures generated code through the service's SSE API, evaluates outputs with deterministic Python evaluators, and writes raw JSON plus Markdown reports for benchmark comparison.

## Current Status

Verified pruning experiment on the 10-case Multi-File benchmark:

- Context pruning reduced measured model tokens by 7.0%.
- pass@1 stayed at 90.0%.
- Benchmark: 10 Multi-File cases.

Latest known report: `reports/ab_pruning_off_vs_pruning_on_20260530_000411.md`.

`pass@3` pruning stability is planned/manual work. Do not treat pass@3 pruning results as available until a real batch report exists.

## What This Evaluates

- **Java generation service**: local service at `localhost:8123` that exposes the code generation SSE endpoint used by the harness.
- **Multi-agent workflow**: benchmark runs default to the Java Multi-Agent path unless `--no-agent` is passed.
- **Generated artifacts**: HTML and multi-file front-end outputs are evaluated with deterministic checks such as tag existence, counts, attributes, text, and regex expectations.
- **A/B configurations**: YAML configs make it possible to compare Java service behavior, including context pruning on/off.

## Architecture

```text
EvalCase JSON
  → Python batch runner
  → JavaServiceClient
  → Java AI service over SSE
  → generated code/files
  → evaluator checks
  → EvalResult JSON
  → Markdown report
```

Key modules:

- `src/llm_codegen_eval/benchmarks/cases.json` stores benchmark cases.
- `src/llm_codegen_eval/clients/java_client.py` calls the Java service.
- `src/llm_codegen_eval/core/batch_runner.py` runs cases and handles repeated generations.
- `src/llm_codegen_eval/core/reporter.py` generates benchmark and A/B Markdown reports.
- `scripts/run_benchmark.py` runs one configuration.
- `scripts/run_ab.py` compares two configurations.

## Prerequisites

- Python `>=3.13`
- `uv`
- Java AI service running locally on `localhost:8123`
- MySQL access to the Java service database when using default chat-history cleanup
- Optional: Prometheus metrics exposed by the Java service for token attribution

Install Python dependencies:

```bash
uv sync
```

## Quick Start

Run the smallest local smoke test:

```bash
uv run python scripts/test_one_case.py
```

Run a limited benchmark against the Java service:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_benchmark.py \
  --name smoke \
  --type multi_file \
  --limit 2 \
  --runs-per-case 1 \
  --infra-retries 1
```

By default, benchmark commands:

- use the Java Multi-Agent workflow;
- clear `chat_history` before each case run;
- read MySQL password from `--mysql-password`, `EVAL_MYSQL_PASSWORD`, or `MYSQL_PWD`;
- save raw results and Markdown reports under `reports/`.

Use `--no-clear-chat-history` only when intentionally measuring behavior with existing conversation state.

## Benchmark Commands

Single-config Multi-File run:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_benchmark.py \
  --name multi_file_baseline \
  --type multi_file \
  --runs-per-case 1 \
  --infra-retries 1
```

Single-config pass@k run:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_benchmark.py \
  --name multi_file_pass3 \
  --type multi_file \
  --runs-per-case 3 \
  --infra-retries 1
```

Pruning A/B smoke run:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --limit 4 \
  --runs-per-case 1 \
  --infra-retries 1
```

Pruning A/B full run:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --runs-per-case 1 \
  --infra-retries 1
```

Manual pass@3 pruning stability run:

```bash
EVAL_MYSQL_PASSWORD='your-password' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --runs-per-case 3 \
  --infra-retries 1
```

Treat provider/network failures, including TLS handshake failures, as infrastructure errors rather than model-quality failures. Use `--infra-retries` to retry transient failures per case run.

## A/B Reports

`scripts/run_ab.py` runs config A then config B sequentially and writes:

- raw JSON results for each side;
- an A/B Markdown report named like `reports/ab_<config-a>_vs_<config-b>_<timestamp>.md`;
- pass-rate deltas, average score deltas, duration deltas, and infrastructure retry totals;
- `pass@k` plus `pass@1` when `--runs-per-case` is greater than 1;
- per-case improvements, regressions, and stability notes.

The pruning configs currently used for comparison are:

- `configs/pruning_off.yaml`
- `configs/pruning_on.yaml`

## Token Attribution

A/B runs capture token usage from Java service Prometheus counters by default when metrics are available. The report records token counter deltas for each sequential config run and compares input, output, and total measured model tokens.

Important caveats:

- token deltas depend on Prometheus counter availability;
- A/B token attribution assumes metric isolation during the run;
- avoid concurrent Java service traffic while collecting token deltas;
- if metrics are unavailable, the benchmark can still produce quality and latency reports without token attribution.

## Repository Layout

```text
configs/                         A/B run configuration files
docs/issues/                     scoped task notes and issue prompts
scripts/run_benchmark.py          single-configuration benchmark runner
scripts/run_ab.py                 two-configuration A/B runner
scripts/test_one_case.py          small end-to-end smoke script
src/llm_codegen_eval/benchmarks/  benchmark case definitions
src/llm_codegen_eval/clients/     Java service client
src/llm_codegen_eval/core/        config, running, metrics, reporting, results
tests/                            offline unit tests
```

## Known Limitations

- The harness requires a separately running Java service for real generation runs.
- Default chat-history cleanup requires MySQL credentials and access to the Java service database.
- Token attribution is only as reliable as the Java service Prometheus counters and isolation of the run window.
- `pass@3` pruning stability is planned/manual until a real full report is generated.
- Vue project cases have a lightweight structural evaluator, but real quality claims still require a live `vue_project` benchmark report.
- Evaluators are deterministic structural checks; they do not replace human review for UX quality, maintainability, or security.

## Demo

- [Three-minute interview demo script](docs/demo-script.md)

## Roadmap

- Complete the manual pass@3 pruning stability run and publish the real report.
- Run and publish a real `vue_project` benchmark using the new VueEvaluator.
- Connect Java-side Vue build metadata into eval reports when available.
- Continue expanding evaluator coverage beyond structural checks.
- Use the demo script as the basis for a concise interview walkthrough.
