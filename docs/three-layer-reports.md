# Three independent evaluation layers

The public CLI can now run the versioned `html-behavior-v1` suite, in addition to legacy `html`.
No Java service, database, GPU or provider key is required for the packaged reference demonstration.

```bash
uv sync --frozen --extra api --dev
uv run playwright install chromium
uv run llm-codegen-eval demo
```

`demo` executes five **hand-written checker reference fixtures**, not model outputs. Its scores
validate the evaluation path only. It prints the unique report directory. The fixtures are packaged
with the tool, so installed CLI users do not need to find files in a source checkout.

## Model or saved-artifact evaluation

```bash
# Provider calls incur normal API charges; no GPU is required.
export INFERENCE_API_KEY='<your-provider-key>'
uv run llm-codegen-eval run --target openai:<model-id> --base-url https://<provider>/v1 \
  --suite html-behavior-v1 --case-id behavior_timer --repeats 3

# For existing complete artifacts named <case-id>.html:
uv run llm-codegen-eval run --target artifacts --artifacts-dir ./my-html \
  --suite html-behavior-v1
```

Behavior-enabled suites run all three layers by default. The original `html` suite has no behavior
contracts; it keeps structural scoring and optional `--smoke`. Explicit `--no-behavior` performs
structural-only diagnostics for a behavior suite (and optional `--smoke`), visibly marking behavior
as `not_run`. Exit 0 in that mode says nothing about unexecuted functionality.

## Layer definitions and denominators

1. **Structural:** declared DOM/source requirements, using the existing evaluator and score.
2. **Smoke:** the self-contained document loads and has no fatal console/page errors at initial load.
   Contract selectors are assessed as structure/behavior, not conflated with this load layer.
3. **Behavior:** declared actions produce specified observable outcomes. Specific checkpoints are
   recorded separately, including dependent checks that did not run.

Each layer reports `passed`, `failed`, `checker_error`, `not_run` and `not_applicable` counts.
Its rate is `passed / (passed + failed)`, or **null/N/A** if no attempts were judged. Read the rate
with the judged count and the other statuses: a 100% rate with many unavailable attempts is incomplete
coverage. Generation failures are counted separately and leave unevaluated layers `not_run`.
A smoke failure skips behavior. Missing browser, unexpected checker exceptions or an incomplete
checker are not model behavior failures. Wrong or ambiguous generated controls are behavior-contract failures, while browser transport and checker failures remain separate. A case can pass structure and smoke but fail behavior.
There is no combined score, and passing these five bounded contracts is not full app correctness.

## Output files

- **report.md:** independent layer summary, per-attempt outcomes, exact failing checkpoints and
  relative links to HTML, final screenshot, browser log and Playwright trace.
- **layers.json:** machine-readable independent counts, denominators, outcomes and diagnostics.
- **results.json:** backward-compatible EvalResult fields plus optional `behavior_result`,
  `browser_evidence` and `browser_diagnostics`. `passed` and `score` still mean **structural** success.
- **structural-report.md:** existing report format, retained for historical tooling. Its legacy
  structural statistics use their original semantics; use layers.json for the independent denominators.
- **run.json:** source kind, workload/case definitions and hash, checker hash, Python/Playwright version,
  and generation parameters. Per-attempt artifact SHA-256 is retained in raw results.
- **artifacts/** and **evidence/**: full HTML and browser evidence, retained for passing and failing cases.

Use `uv run playwright show-trace <run>/evidence/<attempt>/trace.zip` to inspect the interaction trace.
A final screenshot is the state at the end/failure; the trace contains the intermediate interactions.
Evidence-capture errors remain visible and cause a nonzero CLI exit even if assertions passed.
The existing GraphQL API's `passed` field also retains its structural-only meaning.

## Deliberately faulty example (source checkout)

```bash
mkdir -p /tmp/code-eval-pause-fault
cp src/llm_codegen_eval/benchmarks/behavior/fixtures/behavior_timer--ignores-pause.html \
  /tmp/code-eval-pause-fault/behavior_timer.html
uv run llm-codegen-eval run --target artifacts --artifacts-dir /tmp/code-eval-pause-fault \
  --suite html-behavior-v1 --case-id behavior_timer
```

Expected: structure passes, smoke passes, behavior fails at `pause-preserves-time`, exit 1.
This is an intentionally faulty checker-calibration example, not an observed model failure.

## Compatibility and scope

Old raw reports load with optional new fields unset, and old Java generation/A/B/repair commands keep
existing structural definitions. This increment adds single-file HTML contracts; multi-round agent
workspaces, React/Vue builds, broad model rankings, visual judging and statistical significance claims
are outside scope. Browser isolation is not an OS sandbox. Review artifacts/traces before publishing.
