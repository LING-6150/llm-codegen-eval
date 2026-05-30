# Three-Minute Interview Demo Script

This script is for a concise interview walkthrough of the LLM codegen evaluation harness and the context-pruning A/B result.

## Setup Before The Demo

- Java AI service is running on `localhost:8123`.
- MySQL is reachable for `chat_history` cleanup.
- `uv` dependencies are installed.
- No other traffic is using the same Java service `appId` while token metrics are captured.
- Latest known result from `EVAL_HARNESS_NOTES.md`: pass@1 stayed at 90.0% and measured total tokens decreased by 7.0% on the 10-case `multi_file` benchmark.

## 0:00-0:30 — Frame The Problem

Say:

> This repo is an evaluation harness for LLM code generation. The goal is to test generated code with repeatable benchmark cases instead of judging demos by screenshots or vibes.

Show the benchmark file:

```bash
sed -n '1,120p' src/llm_codegen_eval/benchmarks/cases.json
```

Talking points:

- `cases.json` is the source of truth for benchmark prompts, code type, difficulty, required checks, optional checks, and forbidden patterns.
- The suite currently contains 30 cases: 15 `html`, 10 `multi_file`, and 5 `vue_project` cases.
- The pruning result being discussed is specifically for the 10-case `multi_file` slice, not the entire benchmark.

## 0:30-1:20 — Explain The A/B Run

Say:

> The experiment compares the same agentic code-generation flow with context pruning disabled versus enabled. The runner clears chat history before each case, runs both configs sequentially, evaluates pass/fail, and captures Prometheus token counter deltas around each config run.

Show the configs and runner:

```bash
cat configs/pruning_off.yaml
cat configs/pruning_on.yaml
sed -n '1,120p' scripts/run_ab.py
```

Run command for a full one-run-per-case demo:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --runs-per-case 1 \
  --infra-retries 1
```

Optional shorter smoke command if interview time is tight:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --limit 4 \
  --runs-per-case 1 \
  --infra-retries 1
```

Talking points:

- `--type multi_file` selects the 10 multi-file tasks.
- `--runs-per-case 1` makes this a pass@1 interview demo.
- `--infra-retries 1` retries transient provider or network failures once per case run.
- Chat history cleanup is enabled by default so each case starts clean.
- Token metrics are enabled by default and are attributed by sequential A then B runs.

## 1:20-2:10 — Read The Report

Say:

> The runner saves raw JSON for both variants and a Markdown A/B report under `reports/`. I look first at pass rate, then token usage, then infra retries and caveats.

After the command finishes, open the report path printed by the runner:

```bash
sed -n '1,220p' reports/ab_pruning_off_vs_pruning_on_YYYYMMDD_HHMMSS.md
```

For the latest known completed run, use this wording:

> On the latest known 10-case `multi_file` run, pass@1 was unchanged at 90.0%. Measured total model tokens decreased by 7.0% with context pruning enabled.

What to point at in the report:

- `Winner Summary` for pass-rate, score, and duration deltas.
- `Summary` for pass@1 and `Infra retries used`.
- `Token Usage` for input, output, and total token deltas.
- `Per-Case Diff` for any task-level regressions or improvements.

## 2:10-2:45 — State The Interpretation

Say:

> The useful takeaway is not that pruning improves correctness. In this run, correctness was flat: pass@1 stayed at 90.0%. The useful result is that pruning reduced measured model token usage by 7.0% while preserving pass@1 on this benchmark slice.

Talking points:

- This is evidence that field-level context pruning can reduce token cost for these multi-file tasks.
- Pass@1 unchanged means no measured quality regression in this run.
- The report keeps raw result paths so the claim is auditable.

## 2:45-3:00 — Caveats And What Not To Claim

Say:

> There are two caveats. First, latency is noisy because provider queues, TLS handshakes, and network conditions can dominate wall-clock time. Second, token attribution assumes no unrelated requests used the same appId during the sequential A/B run.

Do not claim:

- Do not claim pruning universally improves pass rate.
- Do not claim latency improvements unless the report clearly supports them and the environment was controlled.
- Do not claim the 7.0% token reduction applies to all code types; it is the latest known result for the 10-case `multi_file` benchmark.
- Do not treat DeepSeek TLS or provider handshake failures as model-quality failures; treat them as infrastructure errors and check `Infra retries used`.
- Do not cite a new result until a real run has completed successfully and the generated report confirms it.

## Fallback If The Live Run Fails

Say:

> The harness distinguishes generation quality from infrastructure reliability. If a provider TLS or transient network error occurs, I do not count that as a model regression; I rerun or inspect the retry count and raw JSON.

Then show the latest known notes instead of inventing a live result:

```bash
sed -n '1,40p' EVAL_HARNESS_NOTES.md
```

Use this exact fallback claim:

> The checked-in latest known result says context pruning reduced measured model tokens by 7.0%, while pass@1 stayed at 90.0% on the 10-case `multi_file` benchmark.

