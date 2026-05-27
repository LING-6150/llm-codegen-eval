# llm-codegen-eval

Evaluation harness for LLM code generation, modeled after HumanEval/SWE-bench methodology.

## Status

Day 1 milestone: end-to-end pipeline working for HTML cases.

## Architecture

```
EvalCase → JavaServiceClient → Java AI service (SSE) → Generated code → Evaluator → EvalResult
```

## Quick Start

Prerequisites: uv installed, Java service running on localhost:8123

```bash
uv sync
uv run python scripts/test_one_case.py
```

## Roadmap

- [x]  Day 1: Project skeleton, EvalCase/EvalResult schema, HtmlEvaluator MVP, one case end-to-end
- [ ]  Day 2: Convert 30 existing cases to JSON, run baseline
- [ ]  Week 2: Multi-File / Vue evaluators, pass@k, A/B testing
- [ ]  Week 3: Markdown/HTML reports, GitHub Actions CI
- [ ]  Week 4: Context Pruning experiment
