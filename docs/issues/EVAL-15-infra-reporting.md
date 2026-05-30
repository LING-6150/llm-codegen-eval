# EVAL-15 — Infra Error Reporting

GitHub issue: https://github.com/LING-6150/llm-codegen-eval/issues/15

## Scope

Allowed files:

- `src/llm_codegen_eval/core/batch_runner.py`
- `src/llm_codegen_eval/core/reporter.py`
- `src/llm_codegen_eval/core/result.py` only if needed
- Related tests

Avoid:

- Java repo changes
- Real benchmark runs
- Git commit / push / PR

## Drop-in prompt

```
You are a Codex worker for `llm-codegen-eval`.

Task: EVAL-15 / Issue #15 — Eval-side infra error reporting.

Hard rules:
1. Do not git commit.
2. Do not git push.
3. Do not create or close PRs/issues.
4. Only edit files in this issue's allowed scope.
5. Do not modify Java repo.
6. Do not run real Java/LLM benchmark.
7. Do not invent test results.

Read first:
- EVAL_HARNESS_NOTES.md
- src/llm_codegen_eval/core/batch_runner.py
- src/llm_codegen_eval/core/reporter.py
- tests/test_batch_runner.py
- tests/test_ab_reporter.py
- docs/issues/EVAL-15-infra-reporting.md

Goal:
Improve eval reports so transient infrastructure/provider errors are visible separately from model quality failures. Preserve current retry behavior. If `infra_retries_used` support already exists, build on it rather than duplicating it.

Acceptance criteria:
- Reports include actual infra retries used.
- Reports make errored/generation-network failures easy to distinguish from ordinary failed checks.
- Tests cover retry counting and report output.
- Run `uv run pytest` if available; otherwise report exact reason and run compileall or focused fallback.

When done, output exactly:
- Summary
- Changed files
- Tests run
- Risks / caveats
- Suggested notes snippet for EVAL_HARNESS_NOTES.md
- Suggested commit message
```
