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
