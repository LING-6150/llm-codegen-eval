# EVAL-13 — Manual pass@3 Pruning Stability Run

GitHub issue: https://github.com/LING-6150/llm-codegen-eval/issues/13

Do not run this in parallel worker terminals. Run it manually on the machine with:

- Java service running on `localhost:8123`
- MySQL reachable and `chat_history` cleanup password configured
- `uv` available
- no other traffic using the same `appId` during token metric capture

## Smoke

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --limit 4 \
  --runs-per-case 3 \
  --infra-retries 1
```

## Full

```bash
EVAL_MYSQL_PASSWORD='LingMysql123!' uv run python scripts/run_ab.py \
  --config-a configs/pruning_off.yaml \
  --config-b configs/pruning_on.yaml \
  --type multi_file \
  --runs-per-case 3 \
  --infra-retries 1
```

## Completion Checklist

- Save raw A/B JSON paths.
- Save report path.
- Confirm report includes `pass@3`, `pass@1`, token usage, and infra retries used.
- Update `EVAL_HARNESS_NOTES.md` only with real metrics from the report.
