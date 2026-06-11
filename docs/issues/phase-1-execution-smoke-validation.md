# Phase 1: Add Execution Smoke Validation Layer

## Goal

Add an execution smoke validation layer to the eval harness so generated artifacts are checked not only structurally, but also at the most basic runtime/build level.

This is the first phase from `docs/technical-north-star.md`. It should upgrade the benchmark from structural-only validation to a two-tier eval:

1. Structural validation: deterministic checks over generated files.
2. Execution smoke validation: generated artifact can load/build and does not fail at the first runtime layer.

This issue does **not** implement repair, replay fixtures, variance analysis, or a dashboard.

## Motivation

The current harness is intentionally honest about its boundary: structural-validation pass@k is not HumanEval-style execution-based correctness.

The highest-ROI next improvement is to close the biggest false-confidence gap:

> A generated artifact can satisfy structural checks but still fail to run.

Execution smoke checks should catch that class of failure while staying thin, deterministic, and cheap.

## Scope

### HTML / multi-file outputs

Add a Playwright-based smoke evaluator that can run against generated HTML/multi-file artifacts and report:

- page loads successfully;
- no fatal JavaScript console error;
- required key elements exist when the case provides enough information to check them;
- optional screenshot or lightweight artifact for debugging, if cheap and stable.

### Vue / buildable outputs, if already supported by the harness

If the generated artifact has a build step already represented in the repo/harness, add a build gate:

- build succeeds;
- build failure is surfaced as an execution failure.

Do not create a broad per-framework execution platform in this issue.

## Report Contract

Reports must keep structural and execution results separate.

Do not collapse them into one ambiguous pass value.

Recommended fields:

- `structural_pass` / existing score fields remain unchanged;
- `execution_smoke_pass`;
- `execution_failure_type`;
- `execution_failure_detail`;
- optional `execution_duration_seconds`.

Recommended failure types:

- `not_applicable`;
- `load_failure`;
- `console_error`;
- `missing_element`;
- `build_fail`;
- `checker_error`.

Important: `checker_error` is separate from generated-app failure. The execution checker itself is a new reliability surface and must not silently masquerade as an app failure.

## Measurement Boundaries

- This is smoke-level execution validation, not full functional correctness.
- Do not describe execution smoke pass as HumanEval-style correctness.
- Do not apply an unbiased pass@k estimator to structural checks in this issue.
- Do not introduce repair-loop semantics in this issue.
- Do not change token attribution semantics.

## Non-Goals

- No repair loop.
- No new Java agent.
- No LLM-as-judge.
- No dashboard.
- No model leaderboard.
- No broad benchmark expansion.
- No multi-round interaction tests.
- No product/SaaS features.

## Acceptance Criteria

- [ ] Execution smoke evaluator exists and is unit-tested where possible.
- [ ] Smoke checks run on at least a small fixture/sample artifact without live LLM/provider calls.
- [ ] Batch/report output distinguishes structural result from execution smoke result.
- [ ] Failure type and failure detail are persisted in raw results or report metadata.
- [ ] Checker/environment failures are distinguishable from generated-app failures.
- [ ] README/RESULTS wording remains honest: structural validation and execution smoke validation are two separate layers.
- [ ] Existing structural evaluator behavior remains backward-compatible.
- [ ] Existing tests pass.

## Suggested Implementation Plan

1. Inspect current evaluator/result/report schema.
2. Add a minimal `ExecutionSmokeResult` structure.
3. Add a Playwright-backed smoke evaluator for generated HTML/multi-file output.
4. Add fixture-level tests for success and common failure categories.
5. Integrate execution smoke result into batch raw output and Markdown reports.
6. Run a small smoke on saved/generated artifacts.
7. Update documentation with the new two-tier eval boundary.

## Review Focus

When reviewing this issue, focus on:

- whether structural and execution metrics are kept separate;
- whether the checker can be flaky and how that is surfaced;
- whether failure categories are diagnostic enough without becoming a full test framework;
- whether any wording overclaims functional correctness;
- whether this stays within Phase 1 and does not drift into repair/replay/dashboard scope.
