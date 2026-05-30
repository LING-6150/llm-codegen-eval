# EVAL-18 — Three-Minute Demo Script

GitHub issue: https://github.com/LING-6150/llm-codegen-eval/issues/18

## Scope

Allowed files:

- New doc under `docs/`, recommended `docs/demo-script.md`
- Optional README link if appropriate

Avoid:

- Code changes
- Inventing benchmark results
- Git commit / push / PR

## Drop-in prompt

```
You are a Codex worker for `llm-codegen-eval`.

Task: EVAL-18 / Issue #18 — Create 3-minute interview demo script.

Hard rules:
1. Do not git commit.
2. Do not git push.
3. Do not create or close PRs/issues.
4. Do not invent experimental results.
5. Prefer docs-only changes.

Read first:
- EVAL_HARNESS_NOTES.md
- README.md
- scripts/run_ab.py
- src/llm_codegen_eval/benchmarks/cases.json
- docs/issues/EVAL-18-demo-script.md

Goal:
Create a concise demo script for interviews. It should show cases.json, run_ab.py command, A/B report/token usage, pass@1 unchanged + token -7.0%, and caveats around latency noise/provider TLS errors.

Acceptance criteria:
- A 3-minute script exists under docs/.
- Includes exact talking points and commands.
- Includes caveats and what not to claim.
- No code changes unless adding a README link.

When done, output exactly:
- Summary
- Changed files
- Tests run
- Risks / caveats
- Suggested notes snippet for EVAL_HARNESS_NOTES.md
- Suggested commit message
```
