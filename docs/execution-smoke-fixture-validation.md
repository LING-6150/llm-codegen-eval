# Execution Smoke Fixture Validation

Issue: #28

This document records the first real-browser validation of the Phase 1 execution smoke layer.

## Scope

This is fixture validation, not a benchmark result.

It verifies that the execution smoke checker can classify known local artifacts correctly:

- known-good HTML -> pass;
- known-bad HTML with fatal console output -> `console_error`;
- known-bad HTML with missing required DOM selectors -> `missing_element`;
- browser/checker launch failure remains covered by unit test as `checker_error`.

No RESULTS.md benchmark claim is added by this validation.

## Environment

Playwright Chromium was installed with:

```bash
uv run playwright install chromium
```

Installed browser paths were present locally:

- `~/Library/Caches/ms-playwright/chromium-1223`
- `~/Library/Caches/ms-playwright/chromium_headless_shell-1223`

## Validation Command

```bash
uv run pytest tests/test_execution_smoke.py -q
```

Result:

```text
10 passed in 2.38s
```

Full suite:

```bash
uv run pytest -q
```

Result:

```text
81 passed in 1.12s
```

## Interpretation

The execution smoke layer is now verified on real local browser fixtures.

It is still smoke-level validation, not full functional correctness. It may be used as the second tier in future benchmark reports, separately from structural pass@k.
