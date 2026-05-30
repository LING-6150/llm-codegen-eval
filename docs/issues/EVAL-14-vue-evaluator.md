# EVAL-14 — VueEvaluator

GitHub issue: https://github.com/LING-6150/llm-codegen-eval/issues/14

## Scope

Allowed files:

- `src/llm_codegen_eval/evaluators/*`
- `src/llm_codegen_eval/core/runner.py`
- `tests/test_*vue*` or adjacent evaluator tests
- Small notes snippet in final output only

Avoid:

- Running real Java/LLM benchmark
- Large schema refactor
- Editing cases unless strictly needed
- Git commit / push / PR

## Drop-in prompt

```
You are a Codex worker for `llm-codegen-eval`.

Task: EVAL-14 / Issue #14 — Implement VueEvaluator for vue_project cases.

Hard rules:
1. Do not git commit.
2. Do not git push.
3. Do not create or close PRs/issues.
4. Only edit files in this issue's allowed scope.
5. Do not run real Java/LLM benchmark.
6. Do not invent test results.
7. Prefer offline unit tests.

Read first:
- EVAL_HARNESS_NOTES.md
- src/llm_codegen_eval/core/runner.py
- src/llm_codegen_eval/evaluators/html_eval.py
- src/llm_codegen_eval/benchmarks/cases.json
- docs/issues/EVAL-14-vue-evaluator.md

Goal:
Add a dedicated VueEvaluator for `vue_project` cases. Keep it small: support existing regex/text checks against generated project text, add basic structure checks such as package.json and src/App.vue where detectable, and wire CodeType.VUE_PROJECT to VueEvaluator.

Acceptance criteria:
- `vue_project` no longer uses HtmlEvaluator.
- Existing case checks still run.
- Evaluator handles generated project text with file delimiters or plain text reasonably.
- Offline tests cover pass/fail behavior.
- Run `uv run pytest` if available; otherwise report exact reason and run a reasonable fallback such as compileall.

When done, output exactly:
- Summary
- Changed files
- Tests run
- Risks / caveats
- Suggested notes snippet for EVAL_HARNESS_NOTES.md
- Suggested commit message
```
