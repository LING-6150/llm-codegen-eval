# v1 Eval Platform Release

This release marks the eval harness as a finished technical artifact for
portfolio/interview use. It is not a new benchmark run.

## What Is Included

- Deterministic structural-validation pass@k for HTML and multi-file artifacts.
- Browser execution smoke validation as a separate second tier.
- One-shot repair from deterministic execution-smoke feedback, reported separately
  from first-shot pass.
- Per-run token and mechanism attribution using Prometheus counter windows.
- Redis/MySQL memory isolation for trustworthy A/B runs.
- Replay / fixture mode for offline report and evaluator validation.
- Failure taxonomy diagnostics that classify which layer failed.
- Canonical claim audit in `RESULTS.md`.

## Final Citable Result

The latest citable benchmark result remains the Redis-isolated context-pruning
rerun from 2026-06-09:

- structural pass@3 preserved at `90.0% -> 90.0%`;
- total tokens effectively flat/slightly lower at `323,192 -> 317,785` (`-1.7%`);
- CodeGen-stage input decreased by about `18%`;
- the earlier pre-isolation `+12.3%` token increase is invalidated as Redis
  chat-memory carryover.

The `-1.7%` total-token change is directional and should not be headlined as a
large token saving. The strongest efficiency claim is the CodeGen-stage input
drop, scoped to the stage context pruning directly controls.

## What Is Diagnostic, Not Benchmark Evidence

- Execution smoke fixture validation proves the checker can classify known local
  browser fixtures; it is not a model-quality result.
- One-shot repair fixture validation proves the repair path preserves
  first-shot/repaired separation; it is not a repair-uplift claim.
- Replay / fixture mode proves offline reproducibility boundaries; it is not a
  live benchmark run.
- Failure taxonomy is read-only report diagnosis; it is not root-cause proof and
  does not change scoring.

## Boundaries To Preserve

- Structural pass@k is not HumanEval-style functional correctness.
- Execution smoke is a smoke-level browser/build sanity layer, not full
  functional testing.
- Repair success is not first-shot pass.
- Infra, checker, and replay failures must not be described as model-quality
  regressions.
- No statistical significance language for small benchmark slices.

## Recommended Resume Wording

> Built and hardened a two-tier eval harness for a Java LLM code-generation
> service, combining deterministic structural pass@k with browser execution
> smoke validation, MySQL/Redis memory isolation, Java health gates, infra retry
> invalidation, replay fixtures, failure taxonomy, and per-run Prometheus token
> attribution. The harness caught Redis chat-memory carryover that had
> contaminated token results, traced it to a Java memory-lifecycle bug, and
> re-established a trustworthy isolated baseline.

## Future Work

Future work should be scoped and optional:

- add opt-in full-artifact sidecars for replaying real live-run outputs;
- add arm-order-randomized confirmation only if claiming stability effects;
- add deeper execution checks only if they remain deterministic and cheap.

Avoid adding dashboards, model leaderboards, LLM-as-judge scoring, broad case
expansion, or product features unless they directly improve verifiability.
