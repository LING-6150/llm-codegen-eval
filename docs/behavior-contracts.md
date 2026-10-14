# Five versioned HTML behavior contracts

Suite: `html-behavior-v1`. Case prompts declare the exact public DOM contract and expected
observable behavior. These are new, explicit contracts, not silent changes to the old structural
case definitions or to historical benchmark results. A case uses `data-testid` so the checker
does not guess at labels/layout or inspect the generated implementation.

| Case | Contract | Known faults calibrated |
|---|---|---|
| behavior_timer | Start, decrement, pause, resume, completion, zero bound, reset/restart | frozen countdown; pause ignored |
| behavior_form | Empty name rejected, invalid email rejected, valid submitted values shown | accepts malformed email; drops receipt values |
| behavior_todo | Ignore blank entries, add, toggle one item, delete only selected item | delete does nothing; toggles every item |
| behavior_filter | Case-insensitive search AND category, zero results, clearing filters | case-sensitive search; OR instead of AND |
| behavior_notes | Fresh state, save/reload, overwrite/reload, clear/reload | save does nothing; clear not persisted |

Definitions and hand-written reference/mutated HTML are under
`src/llm_codegen_eval/benchmarks/behavior`. The 15 artifacts are checker calibration fixtures;
they are not model outputs, a hidden test set, or evidence of model generalization.

## Browser execution

The behavior evaluator runs complete self-contained HTML at a disposable loopback HTTP origin.
Every attempt gets a fresh browser context, including fresh storage. HTTP(S) requests outside that
origin and WebSockets are blocked; service workers are disabled. External libraries/assets are
outside this suite's declared contract. This is browser isolation, not an OS security sandbox;
execute untrusted artifacts in an appropriately isolated environment.

Timer tests install Playwright's controlled clock **before** application code loads, then run
scheduled callbacks using `run_for`. No wall-clock sleep is used to decide countdown correctness.
Interactions and assertions have bounded waits. A reference passing repeatedly and these mutations
failing improves checker confidence; it does not prove the checker catches every possible bug.

Smoke checks initial load and fatal console/page errors. Behavior checks interactions afterwards.
A smoke failure leaves behavior `not_run`; missing browser/environment errors are `checker_error`.
Failed assertions are `failed`; later dependent assertions are `not_run`. Unexpected checker errors
are separate from generated-app behavior failures. Final screenshots, traces, console/page errors,
blocked origins and evidence-capture errors are retained when an evidence directory is supplied.

## Reproduce calibration

```bash
uv sync --frozen --extra api --dev
uv run playwright install chromium
uv run pytest tests/test_behavior.py -q
```

Real-browser tests run every reference and both mutations **three times**: 45 calibration trials.
All mutations must still pass structural and initial smoke checks, then fail at their designated
behavior checkpoint. Additional tests check runtime errors, broken checkers and network policy.
Browser tests do not silently skip if Chromium is missing; CI installs Chromium in a dedicated job.
Use `llm-codegen-eval demo` or `run --suite html-behavior-v1` for [CLI integration and independent layer reports](three-layer-reports.md).

References: [Playwright clock](https://playwright.dev/python/docs/clock),
[Playwright assertions](https://playwright.dev/python/docs/test-assertions).
