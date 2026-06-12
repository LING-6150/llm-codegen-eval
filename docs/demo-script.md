# Three-Minute Interview Demo Script

This script is for a concise walkthrough of the eval harness and the Redis chat-memory carryover incident. It is a walkthrough of committed code and saved reports, not a live generation run.

## Setup Before The Demo

- Java AI service is running on `localhost:8123`.
- MySQL is reachable for `chat_history` cleanup.
- Redis chat memory cleanup endpoint is enabled for eval runs.
- `uv` dependencies are installed.
- No other traffic is using the same Java service `appId` while token metrics are captured.

Latest citable result:

- Two-tier eval is now wired and fixture-validated: structural checks plus browser execution smoke validation.
- Structural pass@3 preserved at `90.0% -> 90.0%`.
- Total tokens were effectively flat/slightly lower after memory isolation (`-1.7%`).
- CodeGen-stage input tokens decreased by about `18%`.
- The earlier pre-#24 `+12.3%` token increase was invalidated as Redis memory carryover.

## 0:00-0:30 - Frame The Problem

Say:

> This repo is an evaluation harness for my Java LLM code-generation service. The goal is not to judge demos by screenshots. The goal is to run controlled A/B checks, attribute tokens per run, and catch cases where the eval itself is contaminated.

Show:

```bash
sed -n '1,120p' src/llm_codegen_eval/benchmarks/cases.json
sed -n '1,80p' RESULTS.md
```

Talking points:

- `cases.json` is the source of truth for prompts and deterministic structural checks.
- These are structural-validation checks, not HumanEval-style unit-test execution.
- The harness now has a second, smoke-level browser tier for load/build sanity; it is reported separately from structural pass@k.
- `RESULTS.md` is the canonical audit table for verified, directional, invalidated, and legacy claims.

## 0:30-1:15 - Explain The Harness

Say:

> The runner compares pruning off vs pruning on against the same Java service. It clears MySQL chat_history and Redis chat memory before every run, retries transient infra failures, checks Java health, and captures Prometheus metrics around each generation attempt.

Show:

```bash
cat configs/pruning_off.yaml
cat configs/pruning_on.yaml
sed -n '1,180p' scripts/run_ab.py
```

Example smoke command:

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

Talking points:

- `--capture-run-tokens` writes per-run `token_summary` and `mechanism_summary`.
- Redis memory cleanup is on by default after the #24 fix.
- Provider/TLS/network failures are infra failures, not model-quality failures.

## 1:15-2:10 - The Measurement Bug

Say:

> The interesting part is that an early pruning run showed tokens increasing by about 12%. Instead of accepting that number, I instrumented the prompt composition and found that most of the CodeGen prompt was not the current task at all. It was carried-over Redis chat memory.

Show:

```bash
sed -n '1,220p' docs/redis-memory-carryover-postmortem.md
```

Talking points:

- Prompt diagnostics showed about `89%` of the CodeGen prompt was carried-over memory in the contaminated run.
- The root cause crossed repo boundaries: Python eval saw the metric anomaly, Java memory lifecycle caused it.
- Product bug: `loadChatHistoryToMemory(...)` returned before `chatMemory.clear()` when MySQL history was empty.
- Fix: clear Redis-backed memory before returning on empty MySQL history, and clear Redis memory before every eval run.

## 2:10-2:45 - Corrected Result

Say:

> After isolation, the earlier +12% token result was invalidated. The corrected result was much more boring, which is exactly the point: pass@3 was preserved, total tokens did not increase, and the CodeGen input that pruning directly controls went down by about 18%.

Show:

```bash
sed -n '1,180p' reports/token_attribution_pruning_off_vs_pruning_on_isolated_sharded_20260609_215316.md
```

Use this wording:

> In the isolated 10-case x 3-run benchmark, structural pass@3 stayed at 90%. Total tokens were effectively flat/slightly lower at -1.7%, while CodeGen-stage input decreased about 18%. The pass@1/run-level improvement was observed, but I do not claim it as established because arm order and time were still confounded.

## 2:45-3:00 - Boundaries

Say:

> The main engineering lesson is that LLM evals need reliability work too. This is a two-tier harness now: deterministic structural validation plus browser execution smoke validation. The smoke layer is useful for catching load/build failures, but it is not full functional correctness. What I can claim is that the harness caught a contaminated baseline, traced it to a product bug, and re-established a trustworthy measurement.

Do not claim:

- Do not claim HumanEval-style functional correctness.
- Do not collapse structural pass@k and execution smoke into one pass number.
- Do not claim broad statistical significance from `n=10`.
- Do not claim the invalidated `+12.3%` token increase as a pruning result.
- Do not headline `-1.7%` total tokens as a large token saving.
- Do not claim the observed pass@1/run-level improvement as established without arm-order-randomized confirmation.
