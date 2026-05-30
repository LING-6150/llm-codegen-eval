# Eval Harness Notes

## Current Result

- Context pruning reduced measured model tokens by 7.0%.
- pass@1 stayed at 90.0% on the 10-case `multi_file` benchmark.
- Latest known report: `reports/ab_pruning_off_vs_pruning_on_20260530_000411.md`.

## Day 7 / Issue #13: pass@3 Pruning Stability

Goal: repeat pruning off vs. pruning on with `--runs-per-case 3` to measure pass@3 and stochastic stability.

Smoke command:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --limit 4 \
  --runs-per-case 3 \
  --infra-retries 1
```

Full command:

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --runs-per-case 3 \
  --infra-retries 1
```

Completion checklist:

- A/B report includes `pass@3` and `pass@1`.
- A/B report includes token usage deltas from Prometheus counters.
- A/B report includes actual `Infra retries used` totals.
- Do not cite results until the real batch finishes successfully.
- Clear `chat_history` before each run; this is the default in `scripts/run_ab.py`.
- Treat DeepSeek TLS handshake failures as infrastructure errors, not model-quality failures.
