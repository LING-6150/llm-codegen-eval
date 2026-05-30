# Eval Parallel Codex Task Pack

Use these scoped task prompts to run multiple Codex terminals against `llm-codegen-eval`.

## Rules

- One terminal per issue.
- Workers must not commit, push, close issues, or create PRs.
- Workers must not run real Java/LLM batches unless the prompt explicitly says so.
- Prefer offline unit tests.
- The integrator merges worktree outputs, updates notes, runs tests, commits, pushes, and opens one PR.

## Current Batch

- `EVAL-14-vue-evaluator.md` → Issue #14
- `EVAL-15-infra-reporting.md` → Issue #15 eval-side reporting only
- `EVAL-16-github-actions-ci.md` → Issue #16
- `EVAL-17-readme-rewrite.md` → Issue #17
- `EVAL-18-demo-script.md` → Issue #18

Issue #13 is a real pass@3 experiment. Do not parallelize the actual benchmark run; run it manually on the machine with Java service, MySQL, `uv`, and stable token metric isolation.
