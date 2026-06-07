# Eval Harness Notes

## Current Result

- Context pruning reduced measured model tokens by 7.0%.
- pass@1 stayed at 90.0% on the 10-case `multi_file` benchmark.
- Latest known report: `reports/ab_pruning_off_vs_pruning_on_20260530_000411.md`.

## Day 7 / Issue #13: pass@3 Pruning Stability

Goal: repeat pruning off vs. pruning on with `--runs-per-case 3` to measure pass@3 and stochastic stability.

Smoke command:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --limit 4 \
  --runs-per-case 3 \
  --infra-retries 1
```

Full command:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --runs-per-case 3 \
  --infra-retries 1
```

Completion checklist:

- A/B report includes `pass@3` and `pass@1`.
- A/B report includes token usage deltas from Prometheus counters.
- A/B report includes actual `Infra retries used` totals.
- Do not cite results until the real batch finishes successfully.
- Clear `chat_history` before each run; this is the default in `scripts/run_ab.py`.
- Treat DeepSeek TLS handshake failures as infrastructure errors, not model-quality failures.

## Issues #14-#18: Offline Eval Harness Polish

### Completed in integration PR

- Added a lightweight `VueEvaluator` for `vue_project` cases.
- Expanded benchmark and A/B reports with infra/provider error counts and retry visibility.
- Added GitHub Actions offline pytest workflow; live Java/LLM benchmarks remain manual.
- Rewrote README around eval-harness architecture, benchmark commands, token attribution, limitations, and roadmap.
- Added `docs/demo-script.md` for a three-minute interview walkthrough.

### Caveats

- Vue evaluation is structural and regex/text based; cite real `vue_project` quality only after a live benchmark report exists.
- `pass@3` pruning stability has not been run yet. Run issue #13 on a trusted personal environment with the correct MySQL password, Java service, `uv`, and metric isolation.
- Do not use company-machine database credentials or guessed passwords for benchmark runs.

## Day 7 / Issue #13 Smoke: pass@3 Pruning Stability on 4 Multi-File Cases

Run date: 2026-05-30

Command:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --limit 4 \
  --runs-per-case 3 \
  --infra-retries 1
```

Artifacts:

- Raw A: `reports/raw_ab_pruning_off_20260530_213315.json`
- Raw B: `reports/raw_ab_pruning_on_20260530_213315.json`
- Report: `reports/ab_pruning_off_vs_pruning_on_20260530_213315.md`

Summary:

| Metric | pruning_off | pruning_on | Delta |
| --- | ---: | ---: | ---: |
| pass@3 | 100.0% | 100.0% | +0.0 pp |
| pass@1 | 100.0% | 100.0% | +0.0 pp |
| run-level pass rate | 100.0% | 100.0% | +0.0 pp |
| avg score | 95.0 | 95.0 | +0.0 |
| avg duration | 64.1s | 72.9s | +8.8s (+13.7%) |
| infra retries used | 1 | 0 | -1 |
| infra/provider errors | 0 | 0 | +0 |
| total tokens | 532,338 | 622,595 | +90,257 (+17.0%) |

Per-case stability:

- `multi_011`: pruning_off 3/3, pruning_on 3/3
- `multi_012`: pruning_off 3/3, pruning_on 3/3
- `multi_013`: pruning_off 3/3, pruning_on 3/3
- `multi_014`: pruning_off 3/3, pruning_on 3/3

Interpretation:

- This smoke run validates that the pass@3 pipeline works end to end with chat history cleanup, infra retry tracking, and token metric capture.
- On this 4-case subset, pruning preserved pass@3 and pass@1 at 100.0%.
- Do not cite token reduction from this smoke run. Token usage increased by 17.0% on the subset, likely because token usage is sensitive to stochastic generation length and the subset is small.
- The strongest token-reduction result remains the earlier 10-case pass@1 run: total tokens -7.0%, pass@1 unchanged at 90.0%.
- Issue #13 should remain open until the full 10-case `runs_per_case=3` benchmark is run, or until the scope is explicitly changed to smoke-only.

## Day 7 / Issue #13 Full Attempt: Invalidated by Empty Fast Failures

Run date: 2026-05-30

Command:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --runs-per-case 3 \
  --infra-retries 1
```

Artifacts:

- Raw A: `reports/raw_ab_pruning_off_20260530_225024.json`
- Raw B: `reports/raw_ab_pruning_on_20260530_225024.json`
- Report: `reports/ab_pruning_off_vs_pruning_on_20260530_225024.md`

Observed report summary:

- pass@3: 90.0% -> 70.0%
- pass@1: 80.0% -> 60.0%
- total tokens: 1,531,947 -> 1,075,398 (-29.8%)

Invalidation reason:

- The pruning_on tail contained repeated near-zero-duration empty failures after `multi_018`.
- Examples from raw B:
  - `multi_018` run 2: 51ms, score 0, empty error
  - `multi_018` run 3: 28ms, score 0, empty error
  - `multi_019` runs 1-3: 17-19ms, score 0, empty error
  - `multi_020` runs 1-3: 14-17ms, score 0, empty error
- Normal multi-file generations take tens of seconds. These failures likely indicate an unhealthy Java/provider/SSE state, not real pruning quality regressions.

Conclusion:

- Do not cite pass@3, pass@1, latency, or token deltas from this full attempt.
- Treat this run as a diagnostic artifact only.
- Keep Issue #13 open.

Follow-up harness changes:

- Add `--case-id` to live runners so failed tail cases can be rerun directly, e.g. `--case-id multi_018,multi_019,multi_020`.
- Add suspicious empty generation reporting for `score=0`, empty code, empty error, and generation duration below 1 second.

## Day 7 / Issue #13 Targeted Recovery: Tail Cases Healthy After Restart

Run date: 2026-06-01

Command:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --case-id multi_018,multi_019,multi_020 \
  --runs-per-case 1 \
  --infra-retries 1
```

Artifacts:

- Raw A: `reports/raw_ab_pruning_off_20260601_213337.json`
- Raw B: `reports/raw_ab_pruning_on_20260601_213337.json`
- Report: `reports/ab_pruning_off_vs_pruning_on_20260601_213337.md`

Summary:

| Metric | pruning_off | pruning_on | Delta |
| --- | ---: | ---: | ---: |
| pass@1 | 100.0% | 100.0% | +0.0 pp |
| run-level pass rate | 100.0% | 100.0% | +0.0 pp |
| avg score | 95.0 | 95.0 | +0.0 |
| avg duration | 84.8s | 69.1s | -15.7s (-18.5%) |
| infra retries used | 0 | 0 | +0 |
| infra/provider errors | 0 | 0 | +0 |
| other generation errors | 0 | 0 | +0 |
| suspicious empty generations | 0 | 0 | +0 |
| total tokens | 40,060 | 75,098 | +35,038 (+87.5%) |

Interpretation:

- The targeted rerun confirms `multi_018`, `multi_019`, and `multi_020` are healthy after service recovery.
- The invalid full attempt's pruning_on tail failures were likely caused by transient Java/provider/SSE run-state issues, not deterministic pruning regressions.
- Do not use this 3-case recovery run for token-reduction claims; the sample is too small and token usage increased.
- Next safe step, if continuing Issue #13, is a targeted pass@3 rerun for `multi_018,multi_019,multi_020` or a fresh full pass@3 run after confirming Java service stability.

## Day 7 / Issue #13 Targeted pass@3 Attempt: Invalidated by Empty Fast Failures

Run date: 2026-06-01

Command:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --case-id multi_018,multi_019,multi_020 \
  --runs-per-case 3 \
  --infra-retries 1
```

Artifacts:

- Raw A: `reports/raw_ab_pruning_off_20260601_214302.json`
- Raw B: `reports/raw_ab_pruning_on_20260601_214302.json`
- Report: `reports/ab_pruning_off_vs_pruning_on_20260601_214302.md`

Invalidation reason:

- pruning_on had `Suspicious empty generations = 9/9`.
- All pruning_on runs returned in 21-28ms with score 0, empty generated code, and empty error.
- pruning_on token delta was exactly 0, confirming the Java service did not reach model calls for this variant.
- pruning_off also showed suspicious empty generations on `multi_020` after one DeepSeek TLS failure on `multi_019`, suggesting the local Java/provider/SSE run state became unhealthy mid-run.

Conclusion:

- Do not cite pass@3, pass@1, latency, or token deltas from this targeted pass@3 attempt.
- Stop rerunning evals until the Java service is restarted and logs around the first suspicious empty generation are inspected.
- The harness correctly flags these as suspicious empty generations, so the report is useful for diagnosis but not for model-quality conclusions.

## Day 9A: Java Silent Empty Generation Guardrails

Date: 2026-06-01

Motivation:

- Issue #13 full and targeted pass@3 attempts exposed repeated near-zero-duration empty generations.
- The eval harness correctly identified these as suspicious, but Java should not silently complete an SSE workflow with empty code and no error.
- Goal for Day 9A is not provider fallback yet. The goal is fail-fast observability: the system may fail, but it must fail with a clear `workflow_error`.

Java changes:

- `OrchestratorAgent`
  - Counts streamed CodeGenAgent tokens and accumulates emitted code.
  - If CodeGenAgent completes with blank code, throws `IllegalStateException`.
  - Existing orchestrator catch path emits a `workflow_error` SSE event, so eval can classify the run as an explicit generation error instead of `0ms empty code`.
  - `workflow_error` detail now includes exception class when the original message is null/blank.
- `AiCodeGeneratorFacade`
  - `processCodeStream` now propagates save/parse failures downstream instead of logging and completing.
  - Empty HTML/Multi-File streams fail fast.
  - Parsed empty Multi-File output fails fast instead of saving no files.
  - TokenStream errors now include exception class fallback when message is null/blank.
- `RefineAgent`
  - TokenStream errors now include exception class fallback when message is null/blank.

Validation:

```bash
./mvnw -q -Dtest=OrchestratorAgentTest,AiCodeGeneratorFacadeUnitTest,RefineAgentTest test
./mvnw -q -DskipTests compile
git diff --check
```

Result:

- Targeted Java tests passed.
- Java compile passed.
- No eval benchmark rerun has been performed after this Java change yet.

Expected next behavior:

- If the Java/provider chain returns an empty stream again, eval should receive an explicit `workflow_error` rather than `score=0`, empty error, empty code, and near-zero duration.
- After restarting Java service, rerun a small targeted recovery before any full pass@3 experiment.

## Day 9B: Provider Failure Resilience Observability

Date: 2026-06-01

Decision:

- Do not add model fallback routing yet.
- Keep pruning experiments clean by first improving classification, retry behavior, and metrics for workflow/provider failures.

Java changes:

- `AiProviderErrorClassifier.classifyWorkflow(...)`
  - Preserves transient provider labels such as `tls_handshake`, `timeout`, `rate_limit`, `connection`, and `provider_unavailable`.
  - Adds workflow-layer labels: `workflow_empty_stream`, `workflow_empty_parse`, and `workflow_error`.
- `AiModelMetricsCollector.recordWorkflowError(...)`
  - Emits `ai_workflow_errors_total{user_id, app_id, agent_name, error_type, context_pruning}`.
- `OrchestratorAgent`
  - Records workflow error metrics whenever the fatal catch path emits a `workflow_error` SSE event.

Eval changes:

- `is_infra_error(...)` now treats these Day 9A workflow guardrails as retryable infra errors:
  - `CodeGenAgent produced empty code stream`
  - `AI returned empty code stream`
- `Parsed multi-file code is empty` is intentionally not treated as infra, because it may be a real model/prompt-format failure rather than provider/SSE instability.

Validation:

```bash
# Java
./mvnw -q -Dtest=AiProviderErrorClassifierTest,AiModelMetricsCollectorTest,OrchestratorAgentTest test
./mvnw -q -DskipTests compile
git diff --check

# Eval
uv run pytest
git diff --check
```

Expected next behavior:

- Empty streaming workflow failures should be explicit `workflow_error` events, counted in Java metrics, and retried once by the eval harness.
- If retries still fail, the report should show infra/provider error counts rather than silent suspicious empty generations.

## Day 9B.1: Targeted Recovery Follow-Up

Date: 2026-06-02

Observed run:

- Command: targeted A/B recovery for `multi_018,multi_019,multi_020`, `runs_per_case=1`, `infra_retries=1`.
- Report: `reports/ab_pruning_off_vs_pruning_on_20260602_202029.md`

Result:

- `pruning_off`: all 3 selected cases passed.
- `pruning_on`: `multi_018` passed, but `multi_019` and `multi_020` still produced suspicious empty generations.
- The report showed `Suspicious empty generations = 2` for `pruning_on`.

Conclusion:

- This run is not valid for pruning metrics.
- Day 9B retry classification partially worked, because `multi_019` did trigger an infra retry.
- However, the final result still had empty generated code with no explicit error, so Java still had one silent empty stream path.

Follow-up Java change:

- Add a controller-level empty SSE guard in `AppController.chatToGenCode(...)`.
- If the service content stream completes without any business event, Java now emits a `workflow_error` payload before the final `done` event.
- Expected eval behavior: this should become retryable/observable instead of another `error=None`, `code_len=0`, near-zero-duration suspicious empty generation.

## Day 9C: Eval Harness Circuit Breaker

Date: 2026-06-02

Trigger:

- After Day 9B.1, targeted tail pass@1 and pass@3 recovery runs succeeded.
- A subsequent full `multi_file` pass@3 A/B run failed after `multi_011 run 3`.
- Report: `reports/ab_pruning_off_vs_pruning_on_20260602_215511.md`

Invalidation reason:

- `pruning_off` produced 28 suspicious empty generations after the first infra retry.
- `pruning_on` produced 30 suspicious empty generations.
- `pruning_on` token delta was 0, confirming the service did not reach model calls for that variant.
- `localhost:8123` was not reachable after the run, indicating Java service/run-state failure rather than pruning quality regression.

Conclusion:

- Do not cite pass@k, latency, score, or token deltas from `20260602_215511`.
- The harness needed a circuit breaker so a long run stops when Java enters a bad state instead of continuing to generate invalid empty results.

Eval changes:

- `run_case(...)`
  - Converts fast empty Java responses into an explicit infra error:
    - empty generated code
    - no workflow error
    - generation duration under 1 second
  - Error text: `Infra error: empty response from Java service`
- `is_infra_error(...)`
  - Treats `empty response from Java service` as retryable infra.
- `run_batch(...)`
  - Adds `max_consecutive_infra_failures`, default `3`.
  - In sequential mode, aborts the batch after the threshold is reached.
  - Raises `BatchRunAborted` with partial results for diagnostics.
- `scripts/run_ab.py` and `scripts/run_benchmark.py`
  - Add `--max-consecutive-infra-failures`.
  - Save partial raw results and reports when a batch aborts.
  - Mark report metadata as invalid for model-quality comparison when aborted.

Validation:

```bash
uv run pytest
PYTHONPYCACHEPREFIX=/private/tmp/eval-pycache python3 -m compileall src tests scripts
git diff --check
```

Next run protocol:

1. Restart Java service.
2. Run a small pass@3 smoke with the circuit breaker:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --limit 2 \
  --runs-per-case 3 \
  --infra-retries 1 \
  --max-consecutive-infra-failures 3
```

3. Only rerun full pass@3 if the smoke has zero suspicious empty generations and no abort.

## Day 9D: Cooldown and Sharded Full-Run Protocol

Date: 2026-06-05

Trigger:

- Day 9C fail-fast worked correctly on a full pass@3 attempt.
- The run aborted after three consecutive infra failures instead of producing a polluted full report.
- Root cause signal remained provider/runtime stability:
  - one DeepSeek TLS/handshake failure
  - followed by fast empty Java service responses
  - Java health was unavailable after abort

Decision:

- Do not change model/provider variables for the pruning experiment yet.
- Add a lightweight eval-side cooldown and define a sharded run protocol.
- Keep Resilience4j fallback/model routing as a later Java reliability task because it can change experiment conditions.

Eval changes:

- `run_batch(...)`
  - Adds `cooldown_seconds`, default `0`.
  - Sleeps before retrying an infra failure.
  - Sleeps between sequential jobs.
- `scripts/run_ab.py` and `scripts/run_benchmark.py`
  - Add `--cooldown-seconds`.
  - Record cooldown in report metadata.

Validation:

```bash
uv run pytest
PYTHONPYCACHEPREFIX=/private/tmp/eval-pycache python3 -m compileall src tests scripts
git diff --check
```

Recommended #13 protocol:

- Use sharded pass@3 instead of one long 10-case run.
- Restart Java or at least verify `/api/actuator/health` between shards.
- Use cooldown to reduce immediate provider retry pressure.

Shard commands:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --case-id multi_011,multi_012 \
  --runs-per-case 3 \
  --infra-retries 1 \
  --max-consecutive-infra-failures 3 \
  --cooldown-seconds 10
```

Repeat with:

- `multi_013,multi_014`
- `multi_015,multi_016`
- `multi_017,multi_018`
- `multi_019,multi_020`

Only merge/cite shard results that have:

- `Batch aborted = False`
- `Suspicious empty generations = 0`
- no unresolved infra/provider errors after retry

## Day 9E: Java Health Gate for Eval Runs

Date: 2026-06-05

Trigger:

- Day 9C/9D made invalid long runs visible and recoverable, but the harness still had to observe infra failures before aborting.
- When Java service health is already down, continuing to send generation requests only wastes time and pollutes partial reports.

Decision:

- Add an eval-side Java health gate.
- Do not change Java service behavior.
- Do not add provider retry, fallback routing, or Resilience4j.
- Keep this as a data-integrity guardrail that does not change model/pruning variables.

Eval changes:

- `JavaServiceClient.health()`
  - GETs `/api/actuator/health` with a short timeout.
  - Returns true only for HTTP 200 with `status == "UP"`.
  - Returns false for connection refused, timeout, non-200, invalid JSON, or non-UP status.
- `run_batch(...)`
  - Adds `health_check`, default `True`.
  - Prechecks Java health before login/run start.
  - Aborts immediately if Java health is down after an infra error.
  - Avoids retrying transient errors into a down Java service.
- `scripts/run_ab.py` and `scripts/run_benchmark.py`
  - Add `--health-check` / `--no-health-check`.
  - Record health-check status in report metadata.

Expected behavior:

- If Java is down before a shard starts, the shard aborts with zero results.
- If Java goes down after a TLS/infra failure, the shard aborts immediately with partial results instead of waiting for three consecutive infra failures.
- Reports remain invalid for model-quality comparison when aborted, but should be cleaner and faster to diagnose.

Validation:

```bash
uv run pytest
PYTHONPYCACHEPREFIX=/private/tmp/eval-pycache python3 -m compileall src tests scripts
git diff --check
```

## Issue #13 Result: Sharded Multi-File pass@3 Pruning Experiment

Date: 2026-06-06

Protocol:

- Benchmark: `multi_file`
- Cases: `multi_011` through `multi_020`
- Runs: `10 cases x 3 runs x 2 configs`
- Config A: `pruning_off`
- Config B: `pruning_on`
- Execution: 5 shards, 2 cases per shard
- Harness guards:
  - chat_history cleanup enabled
  - `--infra-retries 1`
  - `--max-consecutive-infra-failures 3`
  - `--cooldown-seconds 10`
  - health gate enabled

Shard reports:

- `reports/ab_pruning_off_vs_pruning_on_20260605_223240.md` (`multi_011,multi_012`)
- `reports/ab_pruning_off_vs_pruning_on_20260605_225552.md` (`multi_013,multi_014`)
- `reports/ab_pruning_off_vs_pruning_on_20260605_232852.md` (`multi_015,multi_016`)
- `reports/ab_pruning_off_vs_pruning_on_20260606_000544.md` (`multi_017,multi_018`)
- `reports/ab_pruning_off_vs_pruning_on_20260606_002052.md` (`multi_019,multi_020`)

Combined report:

- `reports/ab_pruning_off_vs_pruning_on_sharded_20260606_002052.md`
- Raw A: `reports/raw_ab_pruning_off_sharded_20260606_002052.json`
- Raw B: `reports/raw_ab_pruning_on_sharded_20260606_002052.json`

Validity:

- All shards completed with `Batch aborted = False`.
- Suspicious empty generations: `0 -> 0`.
- Infra/provider errors after retry: `0 -> 0`.
- Infra retries used: `0 -> 1`.
- Java watch log stayed healthy during successful shards:
  - `/api/actuator/health` remained 200
  - FD count stayed near 317-322
  - `:443` connections returned to 0 after shards

Result:

| Metric | pruning_off | pruning_on | Delta |
|--------|-------------|------------|-------|
| pass@3 | 90.0% | 90.0% | +0.0 pp |
| pass@1 | 90.0% | 90.0% | +0.0 pp |
| Run-level pass rate | 90.0% | 90.0% | +0.0 pp |
| Avg score | 85.3 | 85.3 | +0.0 |
| Avg duration | 67.4s | 67.4s | -0.0s (-0.1%) |
| Total tokens | 1,415,805 | 1,562,741 | +146,936 (+10.4%) |

Per-agent token deltas:

| Agent | pruning_off | pruning_on | Delta |
|-------|-------------|------------|-------|
| CodeGenAgent | 1,248,137 | 1,387,129 | +138,992 (+11.1%) |
| RefineAgent | 23,710 | 20,446 | -3,264 (-13.8%) |
| ReviewAgent | 143,958 | 155,166 | +11,208 (+7.8%) |

Interpretation:

- Context pruning did not regress pass@3, pass@1, run-level pass rate, or average score on this sharded multi-file pass@3 experiment.
- The expected token reduction cannot be claimed from this run. Aggregate Prometheus token delta was +10.4%, mostly from `CodeGenAgent`, but raw `EvalResult.total_tokens` is still 0 for each run, so the token effect is not yet supported by per-run attribution or confidence intervals.
- This should be treated as inconclusive token evidence, not as a proven token saving or a proven token regression. A prior valid pass@1 run had the opposite aggregate token sign, reinforcing that per-run token attribution is needed before making a resume claim about token reduction.
- `multi_017` remained a stable quality failure in both configs (`0/3 -> 0/3`), so it is not a pruning regression.
- The valid resume/interview claim from this run is:
  - "I built a sharded pass@3 A/B eval protocol with health gates and infra invalidation. Context pruning preserved pass@3 on multi-file cases, while token savings were inconclusive at this sample size because per-run token attribution was not yet available."

Next technical follow-up:

- Add per-run/per-agent token attribution before rerunning the token-reduction hypothesis.
- Inspect prompt/context payload and `CodeGenAgent` invocation count before and after pruning.

## Day 10A: Eval-Only Per-Run Token Attribution

Date: 2026-06-06

Issue:

- #21 `Measure per-run token attribution for context pruning experiments`

Motivation:

- Issue #13 produced a valid sharded pass@3 result for quality, but token effect was inconclusive.
- Raw `EvalResult.total_tokens` was 0 for all runs because token measurement was only captured as config-level Prometheus counter deltas.
- Per-run token attribution is required before making any token reduction claim or debugging CodeGenAgent token movement.

Decision:

- Implement eval-only per-run attribution first.
- Do not change Java service, provider, model routing, prompts, pruning rules, or Prometheus labels.
- Attribute tokens by bracketing each sequential eval attempt with scoped Prometheus snapshots for the same `appId`.

Semantics:

- `--capture-run-tokens` is opt-in.
- Requires `concurrency=1`; concurrent runs are rejected because Prometheus counter deltas would overlap.
- Snapshot timing:
  - run `before_run` first, including chat_history cleanup
  - capture Prometheus `before` snapshot
  - execute one `run_case` attempt
  - capture Prometheus `after` snapshot
- Retry semantics:
  - every attempt gets its own before/after window
  - the final returned/scored attempt writes `EvalResult.total_tokens`
  - attempts retried away are stored in `run_config["retry_token_summaries"]`
  - if all retries are exhausted and the final result is still an infra failure, that final failed attempt still writes its own token summary
- Counter reset guard:
  - if scoped counter total decreases between before and after, set `run_config["token_capture_error"] = "counter reset/regression"`
  - keep `total_tokens = 0`
- Capture failures:
  - do not fail the case
  - set `run_config["token_capture_error"]`

Raw result fields:

- `total_tokens`
- `run_config["token_summary"]`
  - `input`
  - `output`
  - `total`
  - `by_agent`
  - `by_model`
- optional `run_config["retry_token_summaries"]`
- optional `run_config["token_capture_error"]`

CLI:

- `scripts/run_ab.py`
- `scripts/run_benchmark.py`

New option:

```bash
--capture-run-tokens
```

Report metadata records:

- `Run token attribution`
- `Run token attribution mode`

Validity envelope:

- sequential runs only
- one dedicated `appId`
- no concurrent external traffic for that `appId`
- Prometheus counters must not reset during a run window

Validation:

```bash
uv run pytest
PYTHONPYCACHEPREFIX=/private/tmp/eval-pycache python3 -m compileall src tests scripts
git diff --check
```

Next step:

- Run one small shard with `--capture-run-tokens`.
- Verify raw JSON contains non-zero `total_tokens` and per-agent `token_summary`.

Smoke validation:

- Command: `multi_019,multi_020`, `runs_per_case=1`, `--capture-run-tokens`.
- Report: `reports/ab_pruning_off_vs_pruning_on_20260606_151528.md`
- Raw A: `reports/raw_ab_pruning_off_20260606_151528.json`
- Raw B: `reports/raw_ab_pruning_on_20260606_151528.json`
- Result:
  - `pruning_off` per-run token sum: `20,776`
  - `pruning_on` per-run token sum: `34,452`
  - config-level token deltas matched the per-run sums exactly for this smoke
  - all 4 raw results had non-zero `total_tokens`
  - all 4 raw results had `run_config["token_summary"]["by_agent"]`
  - no `token_capture_error`

Observation:

- On this two-case smoke, pruning_on increased input tokens, driven by `CodeGenAgent`.
- This confirms Day 10A attribution works and gives the next investigation a concrete per-run/per-agent signal.

## Day 10B: Offline Token Attribution Analyzer

Date: 2026-06-06

Issue:

- #21 `Measure per-run token attribution for context pruning experiments`

Motivation:

- Day 10A writes per-run token summaries into raw JSON, but the raw data still needs a repeatable offline analysis path.
- The analyzer must avoid pseudoreplication: repeated runs of the same case are not independent statistical samples.
- The goal is to quantify and localize token movement, not to claim statistical significance from tiny-N smoke runs.

Implementation:

- Added `src/llm_codegen_eval/core/token_analysis.py`.
- Added `scripts/analyze_token_attribution.py`.
- Kept `reporter.py` and the live A/B run path unchanged.

Analysis contract:

- Unit of analysis: per-case mean of valid runs.
- Paired comparison: only cases with at least one valid token run in both arms.
- Aggregates: equal-weight mean across paired cases, not pooled runs.
- No p-values, confidence intervals, or significance claims.
- Percent delta is undefined when the A denominator is 0.

Valid token run predicate:

- Exclude infra/provider errors.
- Exclude other generation errors.
- Exclude runs with `run_config["token_capture_error"]`.
- Exclude runs missing `run_config["token_summary"]`.
- Analyze only final scored attempts; retried-away attempts are counted only in accounted-token cross-checks.

Report output:

- Per-case token comparison.
- By-agent aggregate delta.
- Input/output split.
- Paired direction summary.
- Validity and cross-check table.
- Optional unpaired/excluded run tables.

Cross-check semantics:

- `valid_token_sum`: final scored runs that are valid for paired comparison.
- `accounted_token_sum`: all final attempt tokens plus retried-away attempt tokens.
- Config-level Prometheus totals, when supplied, are checked against `accounted_token_sum`.
- Offline raw-only analysis can still run without config-level totals; the report emits a caveat.

Smoke verification:

```bash
uv run python scripts/analyze_token_attribution.py \
  --raw-a reports/raw_ab_pruning_off_20260606_151528.json \
  --raw-b reports/raw_ab_pruning_on_20260606_151528.json \
  --config-token-total-a 20776 \
  --config-token-total-b 34452 \
  --output /private/tmp/token_attribution_smoke.md
```

Smoke result:

- `pruning_off` accounted token sum: `20,776`, cross-check matched.
- `pruning_on` accounted token sum: `34,452`, cross-check matched.
- `multi_019` and `multi_020` both showed higher `CodeGenAgent` input under pruning_on.
- This remains directional only because it is a 2-case smoke.

Validation:

```bash
uv run pytest
python3 -m compileall src tests scripts
```

Next step:

- Run a larger `--capture-run-tokens` sharded experiment and feed the raw files into `scripts/analyze_token_attribution.py`.
- Use the analyzer to confirm whether the CodeGenAgent input increase persists at the case-mean level.
- If it persists, add Java-side instrumentation for CodeGenAgent invocation count and per-call context size.

## Day 10B.1: Token Analyzer Review Polish

Date: 2026-06-06

Issue:

- #21 `Measure per-run token attribution for context pruning experiments`

Review result:

- Claude reviewed the Day 10B implementation as a correctness review.
- No blockers were found.
- The implementation was kept.

Polish changes:

- Added committed smoke fixtures under `tests/fixtures/`.
- Updated the golden test to load fixture JSON through `load_results()` instead of using synthetic in-memory values.
- Added `Delta % Cases` to the paired direction summary so readers can see when zero-baseline cases were skipped for percentage statistics.
- Added report caveats for:
  - percentage summaries skipping arm-A zero-token baselines
  - per-agent input percentages being high-variance at small baselines

Scope:

- No Java changes.
- No live runner changes.
- No reporter integration.
- No statistical significance claims.

Validation:

```bash
uv run pytest tests/test_token_analysis.py -q
uv run python scripts/analyze_token_attribution.py \
  --raw-a reports/raw_ab_pruning_off_20260606_151528.json \
  --raw-b reports/raw_ab_pruning_on_20260606_151528.json \
  --config-token-total-a 20776 \
  --config-token-total-b 34452 \
  --output /private/tmp/token_attribution_smoke_polish.md
```

Next step:

- Day 10C: run the sharded 10-case pass@3 experiment with `--capture-run-tokens`.

## Day 10C: Sharded pass@3 With Per-Run Token Attribution

Date: 2026-06-06

Issue:

- #21 `Measure per-run token attribution for context pruning experiments`

Protocol:

- 10 multi-file cases: `multi_011` through `multi_020`.
- 3 runs per case.
- A/B configs:
  - A: `configs/pruning_off.yaml`
  - B: `configs/pruning_on.yaml`
- 5 sequential shards:
  - `multi_011,multi_012`
  - `multi_013,multi_014`
  - `multi_015,multi_016`
  - `multi_017,multi_018`
  - `multi_019,multi_020`
- Enabled `--capture-run-tokens`.
- Kept sequential execution to preserve Prometheus per-run token attribution validity.

Included shards:

- `20260606_170047`
- `20260606_172045`
- `20260606_173701`
- `20260606_201650`
- `20260606_184745`

Excluded diagnostic shards:

- `20260606_181533`: unresolved infra/provider error in `pruning_on`.
- `20260606_194618`: DeepSeek `Insufficient Balance` / empty-response cascade after quota exhaustion.

Merged artifacts:

- A raw: `reports/raw_ab_pruning_off_sharded_tokens_20260606_201650.json`
- B raw: `reports/raw_ab_pruning_on_sharded_tokens_20260606_201650.json`
- A/B report: `reports/ab_pruning_off_vs_pruning_on_sharded_tokens_20260606_201650.md`
- Token attribution report: `reports/token_attribution_pruning_off_vs_pruning_on_sharded_20260606_201650.md`

Validity:

- 5/5 included shards completed.
- Batch aborted: `False` for all included shards.
- Final infra/provider errors: `0` vs `0`.
- Other generation errors: `0` vs `0`.
- Suspicious empty generations: `0` vs `0`.
- Valid token runs: `30/30` vs `30/30`.
- Paired cases: `10/10`.
- Token cross-check:
  - `pruning_off`: valid/accounted/config total all `1,365,825`, match.
  - `pruning_on`: valid/accounted/config total all `1,533,768`, match.

Quality result:

- pass@3: `90.0% -> 90.0%` (`+0.0 pp`)
- pass@1: `90.0% -> 90.0%` (`+0.0 pp`)
- run-level pass rate: `90.0% -> 90.0%` (`+0.0 pp`)
- avg score: `94.6 -> 94.6` (`+0.0`)
- `multi_017` remained a stable quality failure in both arms (`0/3 -> 0/3`), so it is not a pruning regression.

Latency result:

- avg duration: `81.8s -> 75.0s`
- delta: `-6.8s` (`-8.3%`)

Token result:

- input tokens: `1,218,967 -> 1,387,583` (`+168,616`, `+13.8%`)
- output tokens: `146,858 -> 146,185` (`-673`, `-0.5%`)
- total tokens: `1,365,825 -> 1,533,768` (`+167,943`, `+12.3%`)

Per-agent token attribution:

- `CodeGenAgent`: `1,199,964 -> 1,377,368` (`+177,404`, `+14.8%`)
- `ReviewAgent`: `143,497 -> 143,914` (`+417`, `+0.3%`)
- `RefineAgent`: `22,364 -> 12,486` (`-9,878`, `-44.2%`)

Per-case token direction:

- `pruning_on` total tokens higher in 5 cases.
- `pruning_on` total tokens lower in 5 cases.
- mean per-case total-token delta: `+25.2%`.
- median per-case total-token delta: `+3.2%`.
- range: `-13.2%` to `+177.2%`.
- The large positive mean is driven primarily by `multi_011` and `multi_012`; the median is much smaller.

Conclusion:

- Context pruning preserved quality on this validated sharded pass@3 benchmark.
- The token-reduction hypothesis was not supported.
- With per-run/per-agent attribution, observed total tokens increased by `+12.3%`, driven by `CodeGenAgent` input (`+16.6%` in the token attribution report).
- This should not be presented as a token-saving result.

Resume/interview-safe phrasing:

- "I built a pass@k A/B eval harness with sharded execution, chat-history isolation, infra failure invalidation, Java health gates, and per-run Prometheus token attribution. In a 10-case x 3-run multi-file benchmark, context pruning preserved pass@3 at 90%, while token savings were not supported; per-agent attribution showed CodeGenAgent input increased, so I reported the null/negative token finding instead of overstating it."

Next step:

- Open a Java-side mechanism issue to explain why `CodeGenAgent` input increased:
  - CodeGenAgent invocation count.
  - per-call prompt/context token size.
  - actual pruned vs unpruned context fields delivered to CodeGenAgent.

## Day 10D: Eval Consumer for CodeGen Mechanism Diagnostics

Date: 2026-06-06

Issue:

- #22 `Instrument CodeGenAgent input-token mechanism for context pruning experiments`

Context:

- Java now emits `ai_agent_prompt_chars_total` when `context.pruning.diagnostics.enabled=true`.
- Existing Java metrics already expose `ai_model_requests_total` and `ai_model_tokens_total`.
- The remaining eval-side gap was converting those counters into per-run, appId-scoped mechanism attribution instead of manually grepping cumulative Prometheus output.

Implementation:

- Extended per-run Prometheus capture from token-only snapshots to diagnostic snapshots:
  - `ai_model_tokens_total`
  - `ai_model_requests_total`
  - `ai_agent_prompt_chars_total`
- Kept `token_summary` unchanged for backward-compatible token analysis.
- Added `run_config["mechanism_summary"]` for each captured run.
- Mechanism summary is grouped by agent and includes:
  - `requests_started`
  - `prompt_chars`
  - `input_tokens`
  - `mean_prompt_chars_per_request`
  - `input_tokens_per_request`
- Extended offline token attribution analysis with a `CodeGen Mechanism` table.

Mechanism classifications:

- `more_codegen_requests`: pruning-on has more `CodeGenAgent` model requests.
- `larger_prompt_per_request`: request count is not higher, but prompt chars/request is higher.
- `tokenization_or_stochastic_effect`: prompt chars/request is not higher, but input tokens/request is higher.
- `no_codegen_input_increase`: no CodeGen input increase signal.
- `unpaired`: mechanism data missing in one or both arms.

Important boundary:

- Raw reports generated before this eval-side change do not contain `mechanism_summary`; they can still be used for token attribution, but not for mechanism attribution.
- A new diagnostics-on smoke/full run is required after this change to populate the `CodeGen Mechanism` table.

Verification:

```bash
uv run pytest tests/test_metrics.py tests/test_batch_runner.py tests/test_token_analysis.py -q
uv run pytest -q
PYTHONPYCACHEPREFIX=/private/tmp/eval-pycache python3 -m compileall src tests scripts
```

Result:

- Targeted tests: `28 passed`
- Full tests: `60 passed`
- Compileall: passed

Next step:

- Re-run a small diagnostics-on smoke after pulling this change:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --case-id multi_019,multi_020 \
  --runs-per-case 1 \
  --infra-retries 1 \
  --max-consecutive-infra-failures 3 \
  --cooldown-seconds 10 \
  --capture-run-tokens
```

- Then analyze the new raw files:

```bash
uv run python scripts/analyze_token_attribution.py \
  --raw-a reports/raw_ab_pruning_off_<timestamp>.json \
  --raw-b reports/raw_ab_pruning_on_<timestamp>.json \
  --config-token-total-a <A total from run_ab output> \
  --config-token-total-b <B total from run_ab output>
```

## Day 11 / #24: Redis Chat Memory Isolation

Date: 2026-06-07

Issue:

- #24 `Isolate Redis chat memory during eval runs`

Why this matters:

- #23A showed that the CodeGen prompt bulk came from LangChain4j memory/history, not from the current `CodeGenInput.buildPrompt()`.
- Diagnostics-on smoke observed:
  - total CodeGen prompt chars: `123,398`
  - memory/history chars: `110,013` (`~89%`)
  - system chars: `8,340`
  - current user/buildPrompt chars: `5,045`
  - memory messages: `17`
- The previous eval preflight cleared MySQL `chat_history`, but did not clear Redis `RedisChatMemoryStore`.
- `ChatHistoryServiceImpl.loadChatHistoryToMemory()` returns early when MySQL history is empty, so `chatMemory.clear()` is skipped in the eval state.
- Therefore the shared appId can retain Redis `MessageWindowChatMemory` across case runs and across the A -> B arm boundary.

Impact on previous token conclusions:

- #13/#22 pass@k and score observations remain useful as quality measurements, but token deltas from pre-#24 runs are provisionally invalidated for pruning-token claims.
- The observed `+12.3%` total-token delta and `+14.8%` CodeGenAgent delta may be driven by Redis memory carryover rather than context pruning.
- Do not cite token savings or token regression until the A/B benchmark is rerun with Redis memory isolation enabled.

Implementation:

- Java:
  - Added diagnostics-gated endpoint:
    - `POST /api/diagnostics/chat-memory/clear?appId=<appId>`
  - The endpoint calls `RedisChatMemoryStore.deleteMessages(appId)`.
  - Endpoint is gated by `context.pruning.diagnostics.enabled`; when disabled, it returns a forbidden response and does not clear memory.
- Eval:
  - Added `JavaServiceClient.clear_chat_memory()`.
  - Added Redis memory cleanup to `run_ab.py` and `run_benchmark.py` preflight.
  - Cleanup order before each run:
    1. clear MySQL `chat_history`
    2. clear Redis chat memory
    3. start generation
  - Added CLI controls:
    - `--clear-redis-memory` (default)
    - `--no-clear-redis-memory`

Verification:

```bash
# Java
./mvnw -q -Dtest=DiagnosticsControllerTest,AiModelMonitorListenerTest,AiModelMetricsCollectorTest test
./mvnw -q -DskipTests compile
git diff --check

# Eval
uv run pytest -q
PYTHONPYCACHEPREFIX=/private/tmp/eval-pycache python3 -m compileall src tests scripts
git diff --check
```

Result:

- Java targeted tests: passed.
- Java compile: passed.
- Eval tests: `63 passed`.
- Eval compileall: passed.

Next step:

- Restart Java with `context.pruning.diagnostics.enabled=true`.
- Run a diagnostics-on smoke with default Redis cleanup.
- Verify first CodeGen request after cleanup has memory messages absent/zero and memory chars absent/near zero.
- Only after that, rerun the sharded pass@3 pruning A/B benchmark for a trustworthy token delta.
