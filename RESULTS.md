# Results And Claim Audit

This file is the canonical source for benchmark claims in this repo.

Status legend:

- Verified: backed by an isolated report and safe to cite with scope.
- Directional: useful signal, but not a headline claim.
- Invalidated: useful only as part of the debugging story.
- Legacy: early informal or pre-harness measurement; do not use as a current result.

| Claim | Status | Scope | Evidence | Notes |
|---|---|---|---|---|
| Structural pass@3 preserved at `90.0% -> 90.0%` | Verified | 10 `multi_file` cases x 3 runs, Redis/MySQL memory isolated | `reports/ab_pruning_off_vs_pruning_on_isolated_sharded_20260609_215316.md` | Structural-validation pass@3, not execution-based functional correctness. |
| Total tokens `323,192 -> 317,785` (`-1.7%`) | Directional | Same isolated sharded run | `reports/token_attribution_pruning_off_vs_pruning_on_isolated_sharded_20260609_215316.md` | Effectively flat/slightly lower; do not headline as a large token saving. |
| CodeGen-stage input decreased by about `18%` | Verified within scope | Same isolated sharded run; per-case mean token attribution | `reports/token_attribution_pruning_off_vs_pruning_on_isolated_sharded_20260609_215316.md` | This is the input stage context pruning directly controls. |
| CodeGen mechanism showed no input increase in `10/10` cases | Verified within scope | Same isolated sharded run | `reports/token_attribution_pruning_off_vs_pruning_on_isolated_sharded_20260609_215316.md` | Requests stayed `1 -> 1`, prompt chars/request and input tokens/request decreased in every paired case. |
| pass@1/run-level pass improved in the isolated rerun | Directional | Same isolated sharded run | `reports/ab_pruning_off_vs_pruning_on_isolated_sharded_20260609_215316.md` | Observed only; not claimed as a pruning effect because A ran before B in each shard and `n=10` is small. |
| Prompt-composition diagnostics found CodeGen prompt was about `89%` carried-over memory before isolation | Verified diagnostic | Diagnostics-on smoke before Redis cleanup | `EVAL_HARNESS_NOTES.md` Day 11 | Explains why earlier token measurements were contaminated. |
| Pre-#24 sharded run showed total tokens `+12.3%` and CodeGen `+14.8%` | Invalidated | Sharded run before Redis memory isolation | `reports/token_attribution_pruning_off_vs_pruning_on_sharded_20260606_201650.md` | Contaminated by Redis `MessageWindowChatMemory` carryover; cite only as the invalidated anomaly. |
| Early pass@1 run showed `-7.0%` tokens and pass@1 `90%` | Invalidated | Early run before Redis memory isolation and per-run mechanism diagnostics | `reports/ab_pruning_off_vs_pruning_on_20260530_000411.md` | Superseded by the isolated rerun; do not use as a current token claim. |

## Safe Resume Wording

> Built and hardened a sharded pass@k A/B eval harness for a Java LLM code-generation service, including MySQL/Redis memory isolation, Java health gates, infra retry invalidation, and per-run Prometheus token attribution. After discovering that Redis chat-memory carryover polluted earlier token results, added prompt-composition diagnostics, fixed the Java memory lifecycle bug, and reran an isolated 10-case x 3-run benchmark: structural pass@3 stayed at 90%, CodeGen-stage input dropped about 18%, and total tokens did not increase.

## Explicit Boundaries

- This benchmark uses deterministic structural checks; it is not HumanEval-style execution-based correctness.
- The benchmark is small and directional. Avoid statistical significance language.
- The invalidated token deltas are part of the reliability story, not current performance claims.
- Keep this file updated before adding new numbers to the README or resume.
