# EVAL-17 — README Rewrite

GitHub issue: https://github.com/LING-6150/llm-codegen-eval/issues/17

## Scope

Allowed files:

- `README.md`
- Optional `EVAL_HARNESS_NOTES.md` snippet in final output only

Avoid:

- Code changes
- Inventing benchmark results
- Claiming pass@3 until real run exists
- Git commit / push / PR

## Drop-in prompt

```
You are a Codex worker for `llm-codegen-eval`.

Task: EVAL-17 / Issue #17 — Rewrite README for production-style demo.

Hard rules:
1. Do not git commit.
2. Do not git push.
3. Do not create or close PRs/issues.
4. Only edit README.md.
5. Do not invent experimental results.
6. Mention pass@3 only as planned/manual unless real report exists.

Read first:
- README.md
- EVAL_HARNESS_NOTES.md
- scripts/run_ab.py
- src/llm_codegen_eval/core/reporter.py
- docs/issues/EVAL-17-readme-rewrite.md

Goal:
Rewrite README to position the repo as an eval harness for a Java multi-agent code generation system. Include architecture, quickstart, benchmark commands, A/B reports, token attribution, known limitations, and roadmap.

Must include the verified result exactly:
- Context pruning reduced measured model tokens by 7.0%.
- pass@1 stayed at 90.0%.
- Benchmark: 10 Multi-File cases.

Acceptance criteria:
- README is clear for recruiters/interviewers.
- Does not overclaim pass@3 or VueEvaluator if not implemented yet.
- Commands are accurate for `uv` workflow.
- No code changes.

When done, output exactly:
- Summary
- Changed files
- Tests run
- Risks / caveats
- Suggested notes snippet for EVAL_HARNESS_NOTES.md
- Suggested commit message
```
