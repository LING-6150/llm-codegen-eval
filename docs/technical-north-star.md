# Technical North Star

This document defines the ideal technical direction for this repo after the Redis memory-carryover incident.

It is intentionally not a product roadmap. The goal is not to add SaaS features, dashboards, model leaderboards, or more agent names. The goal is to turn this project into a defensible LLM code-generation reliability harness:

> generate code -> execute-check it -> repair once from deterministic feedback -> re-check it -> measure quality, cost, and failure mode -> preserve replayable evidence.

Use this file as the tie-breaker when future ideas compete for attention.

## Target Shape

The strongest version of this project has five layers.

### 1. Generation System

The Java service remains the system under test:

- Spring Boot code-generation backend.
- SSE generation flow.
- Redis/MySQL chat memory.
- Multi-agent generation path.
- Prometheus/Grafana observability.

This repo does not need to become a user-facing SaaS product. The Java system exists so the eval harness can test a realistic LLM backend.

### 2. Structural Evaluation

The current deterministic evaluator remains useful:

- Generated files exist.
- Required HTML/CSS/JS/Vue structure is present.
- Text, tags, counts, attributes, and regex expectations match the case spec.

Structural checks are cheap, deterministic, and good at catching missing artifacts. They are not functional correctness.

### 3. Execution Smoke Evaluation

The next major technical step is execution-aware validation.

For HTML / multi-file outputs:

- Open the generated page with Playwright.
- Assert the page loads.
- Assert there is no fatal JavaScript console error.
- Assert required key elements exist.
- Save a small execution result artifact.

For Vue outputs:

- Run the build gate.
- Treat build failures as execution failures.

The report should show structural and execution results separately. Do not merge them into one ambiguous pass number.

### 4. One-Shot Repair Loop

If execution smoke fails, the system may attempt exactly one repair pass.

Rules:

- Repair is optional and flag-gated.
- Repair uses deterministic feedback only: console error, missing element, build error, failing path.
- Do not use an LLM judge to summarize or reinterpret failures.
- Do not add unlimited repair loops.
- Prefer reusing the existing refine / retry path instead of adding a new agent role.

Metrics must be split:

- first-shot execution pass rate;
- pass-after-one-repair rate;
- repair uplift;
- extra repair input/output/total tokens;
- extra repair duration.

Never report a repaired result as plain pass@1 without disclosing that repair was allowed.

### 5. Reproducible Evidence Layer

Every important run should leave enough evidence to inspect or replay the evaluator:

- case config;
- generated files;
- structural result;
- execution result;
- token attribution;
- prompt / mechanism summary when available;
- repair result when applicable;
- failure category.

Long-term target: a replay mode that re-runs evaluator and report logic from saved artifacts without calling the Java service or an LLM provider.

## Ideal Phases

### Phase 1: Execution Smoke Layer

Acceptance:

- Playwright or build-based smoke checks run on saved generated artifacts.
- Reports show structural pass and execution smoke pass separately.
- Execution failures have deterministic categories such as `load_failure`, `console_error`, `missing_element`, or `build_fail`.
- RESULTS.md clearly labels this as smoke-level execution, not full functional testing.

This is the highest-ROI next improvement.

### Phase 2: One-Shot Repair

Acceptance:

- Repair is triggered only by deterministic execution feedback.
- Repair is limited to one attempt.
- First-shot pass and pass-after-repair are separate report fields.
- Repair token cost is attributed separately from first-shot generation.
- Repair-off behavior remains comparable to the existing benchmark.

This is the main agentic-codegen improvement. It is only valuable after Phase 1 exists.

### Phase 3: Pass@k And Variance Hygiene

Acceptance:

- HumanEval-style unbiased pass@k estimation is used only where it matches the measured layer.
- Execution pass@k and structural pass rate are not conflated.
- Reports include basic run-to-run variance for score, tokens, duration, and execution smoke pass.

Important: do not imply HumanEval-style functional correctness unless the measured signal is execution-based.

### Phase 4: Replay / Fixture Mode

Acceptance:

- Saved artifacts can be used to re-run evaluator and report code without live Java or provider calls.
- CI can test evaluator/report behavior from fixtures.
- Replay mode is explicitly scoped to eval logic, not model quality.

This is what turns scripts into an eval platform.

### Phase 5: Failure Taxonomy

Acceptance:

- Reports consistently distinguish infra failures, provider/model failures, empty generations, structural failures, execution failures, checker failures, repaired successes, and repair failures.
- When a benchmark turns red, the report says which layer failed.

The point is diagnosis, not just scoring.

### Phase 6: Documentation And Release

Acceptance:

- README, RESULTS.md, postmortems, and demo script agree on the same numbers.
- Every headline claim links to a report or artifact.
- Invalidated results remain visible only as invalidated evidence.
- A release tag marks the project state.

## Professional Caveats To Preserve

These are not optional details. They protect the measurement-integrity story.

### Pass@k Must Be Layer-Specific

Unbiased pass@k is appropriate for execution-style correctness signals. If it is applied to structural checks, the report must say so plainly and avoid HumanEval-style implication.

Preferred rule:

- structural layer: report structural pass rate / structural pass@k with explicit boundary;
- execution layer: report execution smoke pass and, if applicable, execution pass@k.

### Repair Tokens Must Be Isolated

Repair deliberately feeds previous failure output and error feedback into the next prompt. This resembles the same class of contamination as the Redis carryover bug, except it is intentional.

Therefore:

- first-shot CodeGen tokens and repair tokens must be reported separately;
- repair prompt input must not leak into first-shot attribution;
- pass-after-repair must never be described as first-shot pass.

### The Checker Also Needs Reliability

Execution smoke checks introduce a new failure surface. A flaky browser checker can create false failures.

Therefore:

- distinguish generated-app failures from checker/environment failures when possible;
- use deterministic waits and bounded retries;
- keep smoke checks thin;
- add self-tests / fixtures for the checker itself.

The project theme is that eval harnesses need reliability engineering too. New validation layers must be validated.

## Explicit Non-Goals

Do not spend project energy on:

- SaaS product features such as login, payments, onboarding, templates, or dashboards;
- LLM-as-judge quality scoring;
- model leaderboards;
- broad RAG additions;
- more agent roles without a new deterministic signal;
- unlimited multi-round repair;
- large benchmark expansion just to increase N;
- Kubernetes or microservice theater;
- UI polish unrelated to verifiability.

If an idea does not improve verifiability, reproducibility, failure diagnosis, or cost attribution, it belongs in future work rather than the current technical core.

## Final Positioning

The ideal finished project should be described as:

> an execution-aware reliability harness for LLM code generation, with structural validation, browser/build smoke checks, one-shot repair from deterministic feedback, token/cost attribution, failure taxonomy, and replayable evidence.

The project is strongest when it proves how the LLM system behaves, not when it tries to look like a generic app generator.
