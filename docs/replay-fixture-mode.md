# Replay And Fixture Mode

Replay / fixture mode is a reproducibility layer for the eval harness. It is not a
new benchmark result.

## What It Does

- `scripts/replay_report.py` re-renders saved raw JSON into a Markdown report.
- `scripts/replay_artifacts.py` re-runs structural evaluators over complete
  generated-code fixtures.
- Artifact replay can optionally run execution smoke checks when Chromium is
  available.

## What It Does Not Do

- It does not call the Java service.
- It does not call an LLM provider.
- It does not touch MySQL, Redis, Prometheus, or cleanup subprocesses.
- It does not create a new quality, token, or repair-uplift claim.

## Why Raw JSON Is Report-Only

Raw result JSON keeps file sizes small by truncating large `generated_code`
payloads. New raw files include `generated_code_truncated` so replay code can
distinguish complete artifacts from lossy report records.

Report-only replay can safely use raw JSON because it re-renders saved
`EvalResult` fields. Evaluator replay requires complete generated artifacts from
fixtures or future sidecar files.

## Verification

The replay tests prove the important boundaries:

- importing replay/report IO does not import the live batch runner, Java client,
  metrics, runner, preflight, evaluator, or Playwright paths;
- report-only replay succeeds while `httpx.AsyncClient` and `subprocess.run` are
  monkeypatched to fail on use;
- truncated generated code cannot be silently re-evaluated;
- complete good/bad HTML fixtures can be structurally replayed offline.

This is the first step toward making the harness replayable in CI without a live
Java service or provider credentials.
