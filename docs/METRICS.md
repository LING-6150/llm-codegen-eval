# Metrics & Reporting Semantics

This document defines every metric label that appears in the generated reports, and—just as important—what each one **does not** claim. The guiding rule: structural validation, execution smoke, and one-shot repair are three separate layers and are never collapsed into a single ambiguous pass number.

> **Top-level boundary.** This harness measures **structural-validation pass@k**, not HumanEval-style execution-based functional correctness. Execution smoke is a thin browser/build sanity layer, not functional testing. No metric here should be cited as "functional correctness".

---

## Structural pass metrics

Let a *case* be run `N` times (`runs_per_case = N`). For one case, `c` of those `N` runs pass structural validation.

| Report label | Definition | Reads as | Does **not** mean |
|---|---|---|---|
| **First-run structural pass rate** | Fraction of cases whose **first** run passed structural validation. | "If you sampled once, how often is it right." | Not a low-variance estimate — it ignores runs 2..N. |
| **Structural any-of-N pass rate** | Fraction of cases with **≥1** passing run across all N runs. | "Best-of-N reachability." | **Not** HumanEval pass@k and not comparable to it. It is an empirical "at least one of N", which is why it is *not* labeled `pass@N`. |
| **Structural pass@1 estimate (unbiased, all runs)** | Chen et al. unbiased pass@1 estimator, computed **per case** (`k=1 ⇒ c/N`) and then **averaged over cases**. | "Single-sample pass probability, using all the data." | Not pooled (see below). Not execution/functional correctness — it is structural only. |
| **Run-level pass rate** | Passing runs ÷ total runs, pooled across everything. | Raw aggregate. | Not a per-case metric; cases with more runs weigh more. |

### Why three structural numbers, not one
- **First-run** preserves the historical metric so past reports stay comparable (no silent metric drift).
- **any-of-N** answers a different question (reachability), so it gets a different name.
- **unbiased pass@1** is the statistically cleanest single-sample estimate and uses all N runs instead of throwing away N−1 of them.

### Per-case averaging, not pooled
The unbiased estimate is `mean over cases of estimate_pass_at_k(N_i, c_i, k)`. It is **not** a global pooled ratio. Pooling would let high-N or easy cases dominate; per-case averaging gives every case equal weight. Any pooled figure must be labeled "pooled" explicitly.

### k > N is never extrapolated
`estimate_pass_at_k(n, c, k)` returns `None` for `k > n` (and for invalid `n ≤ 0` / `k ≤ 0`), and the report renders `n/a`. The harness never estimates pass@k beyond the number of samples actually collected.

### Single-run reports (N = 1)
When `N = 1`, first-run, any-of-1, and unbiased pass@1 are mathematically identical. The report shows the first-run rate and notes that the unbiased estimate coincides, rather than printing three identical-looking numbers as if they were independent measurements.

---

## Execution smoke metrics

Execution smoke runs the artifact in a real browser (Chromium via Playwright) and is reported **separately** from structural score.

| Report label | Definition |
|---|---|
| **Execution smoke pass rate** | Passed ÷ **judged** runs. |
| **Execution checker errors** | Runs where smoke could not produce an app-level verdict (browser launch/infra failure). |

**Judged set (single source of truth).** A run is *judged* only when smoke ran and produced an app-level verdict: `applicable AND failure_type != "checker_error"`. Checker/infra failures are **excluded from the denominator** — they are never counted as application failures. This predicate lives in exactly one place (`stats.is_execution_judged`) and is reused everywhere, including run-spread; a regression test asserts the literal appears once in `src/`.

Execution smoke is a sanity layer (does it load/build, expected elements present, no console errors). It is **not** functional testing and carries no functional-correctness claim.

---

## One-shot repair metrics

Repair uses execution-smoke feedback **once**. Repaired results live entirely in `RepairSummary` and **never** enter first-shot structural pass@k or the structural score summaries.

| Report label | Definition |
|---|---|
| **First-shot ... / Pass after one repair** | First-shot uses the same judged denominator as execution smoke; pass-after-one-repair counts cases that passed first-shot **or** were fixed by the single repair. |
| **Repair uplift** | `pass_after_one_repair − first_shot_execution_pass`. |
| **Repair attempts/successes** | Efficacy ratio. The **denominator excludes generation/infra failures** (`reason = "repair_generation_error"`) so infra noise does not dilute measured efficacy. Invariant: `succeeded ≤ attempted`. |
| **Repair generation errors** | Infra/generation failures, surfaced **separately** from the efficacy ratio. |
| **Repair token cost** | Tokens attributed to the repair attempt, kept in the repair section only. |

---

## Raw run-to-run spread

Shown only for repeated runs (`N ≥ 2`), per case. **Descriptive only — not a significance test.**

- Score mean ± stdev, duration mean ± stdev.
- First-shot token spread uses `EvalResult.total_tokens`. **Repair token cost is excluded** and stays in the repair section.
- Execution-smoke judged/pass counts when enabled (same judged definition as above).
- Sample standard deviation (`ddof = 1`).

Deliberately **omitted**: confidence intervals, p-values, and any significance language. With small N the spread is noisy; the label says `raw run-to-run spread (descriptive, n=N)` to avoid implying statistical precision.

---

## One-line summary of the boundaries
- Structural ≠ functional correctness. Execution smoke ≠ functional testing.
- any-of-N ≠ HumanEval pass@k.
- Unbiased pass@k is per-case averaged, never pooled, never extrapolated past N.
- Repaired results never enter first-shot metrics; generation errors never enter the efficacy denominator or first-shot token spread.
- Spread is descriptive, not significance.
