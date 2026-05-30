# EVAL-16 — GitHub Actions Offline CI

GitHub issue: https://github.com/LING-6150/llm-codegen-eval/issues/16

## Scope

Allowed files:

- `.github/workflows/*`
- README or notes snippet only if necessary
- Tests only if needed for CI stability

Avoid:

- Live Java service / LLM benchmark in CI
- Secrets in workflow
- Git commit / push / PR

## Drop-in prompt

```
You are a Codex worker for `llm-codegen-eval`.

Task: EVAL-16 / Issue #16 — Add GitHub Actions offline CI.

Hard rules:
1. Do not git commit.
2. Do not git push.
3. Do not create or close PRs/issues.
4. Only edit files in this issue's allowed scope.
5. CI must not run live Java/LLM benchmark.
6. Do not invent test results.

Read first:
- pyproject.toml
- README.md
- tests/
- docs/issues/EVAL-16-github-actions-ci.md

Goal:
Add a GitHub Actions workflow that installs uv/Python and runs offline tests (`uv run pytest`). It should make clear that live LLM/Java evals are manual.

Acceptance criteria:
- Workflow exists under `.github/workflows/`.
- CI runs offline pytest only.
- No Java service, MySQL, or provider secrets are required.
- Run `uv run pytest` locally if available; otherwise report exact reason.

When done, output exactly:
- Summary
- Changed files
- Tests run
- Risks / caveats
- Suggested notes snippet for EVAL_HARNESS_NOTES.md
- Suggested commit message
```
