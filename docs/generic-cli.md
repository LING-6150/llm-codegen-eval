# Public CLI: API generation and saved HTML

Install with `uv sync --frozen --dev`. No Java, MySQL, Redis, Prometheus, GPU or API key is
needed for the saved-artifact example. Python 3.13 remains required in this increment.

```bash
uv run llm-codegen-eval --help
uv run llm-codegen-eval list-cases --suite html
uv run llm-codegen-eval run --target artifacts --artifacts-dir examples/html \
  --suite html --case-id html_001
```

The example is a hand-written fixture and checks structural requirements only. A passing result
is not a model benchmark or proof of functional correctness. Add `--smoke` for the existing browser
load/selector check after installing Chromium: `uv run playwright install chromium`.

For any compatible streaming chat-completions server:

```bash
export INFERENCE_API_KEY='<your-provider-key>'
uv run llm-codegen-eval run --target openai:<provider-model-id> \
  --base-url https://<provider>/v1 --suite html --case-id html_001
```

`OPENAI_API_KEY` is a fallback. Default endpoint is `https://api.openai.com/v1`; change it explicitly
for another provider/local vLLM server. Local servers may omit authentication. Providers must support
streamed chat completions and streamed usage options. API runs incur the provider's normal charges.
`--timeout` bounds the entire generation attempt, not just individual network reads.
No automatic retries are hidden in the results. CLI-agent workspace adapters are not implemented yet.

Use repeated `--case-id`, `--limit`, `--repeats`, `--max-tokens`, `--temperature` and `--seed`
to control the workload. `--output-dir` defaults to `reports/runs`. Each completed run has:

- `run.json`: source kind, parameters, full case definitions and workload hash;
- `results.json`: existing EvalResult JSON, retaining structural semantics;
- `report.md`: existing Markdown report;
- `artifacts/<case-id>-r<attempt>.html`: complete generated artifacts for later evaluation.

Reports are published in a unique directory only after all files are written. Incomplete runs retain
a hidden `.pending-*` directory for diagnosis. Output metadata does not store API keys. Generated
artifacts themselves can contain sensitive user/model content; review before publishing.
Artifact mode expects `<case-id>.html` and refuses path escapes or files larger than 2 MiB.

Exit codes: 0 for all requested checks passing; 1 for generation/evaluation failures; 2 for invalid
configuration. Structural failure still writes a report. A run with `--smoke` also fails on smoke/checker
errors, without changing structural scores. Missing browsers are not treated as generated-code defects.

## Existing Java workflow

The original `scripts/run_benchmark.py` and `scripts/run_ab.py` commands remain available with their
existing health, cleanup and token-capture behavior. The new CLI does not silently reuse or bypass
those isolation guarantees. Java evaluations are still configured through those original commands.
