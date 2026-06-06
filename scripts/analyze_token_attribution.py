"""Analyze per-run token attribution from saved A/B raw result JSON files."""

import argparse
from datetime import datetime
from pathlib import Path

from llm_codegen_eval.core.batch_runner import load_results
from llm_codegen_eval.core.token_analysis import (
    analyze_token_attribution,
    render_token_attribution_markdown,
)


def main(
    raw_a: Path,
    raw_b: Path,
    name_a: str,
    name_b: str,
    output: Path | None = None,
    config_token_total_a: int | None = None,
    config_token_total_b: int | None = None,
):
    results_a = load_results(raw_a)
    results_b = load_results(raw_b)
    analysis = analyze_token_attribution(
        results_a,
        results_b,
        name_a=name_a,
        name_b=name_b,
        config_token_summary_a=_summary(config_token_total_a),
        config_token_summary_b=_summary(config_token_total_b),
    )
    report = render_token_attribution_markdown(analysis)
    output_path = output or _default_output_path(name_a, name_b)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Token attribution report saved to: {output_path}")


def _summary(total: int | None) -> dict[str, int] | None:
    if total is None:
        return None
    return {"total": total}


def _default_output_path(name_a: str, name_b: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("reports") / f"token_attribution_{name_a}_vs_{name_b}_{timestamp}.md"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze per-run A/B token attribution")
    parser.add_argument("--raw-a", type=Path, required=True, help="Raw JSON results for arm A")
    parser.add_argument("--raw-b", type=Path, required=True, help="Raw JSON results for arm B")
    parser.add_argument("--name-a", default="pruning_off", help="Display name for arm A")
    parser.add_argument("--name-b", default="pruning_on", help="Display name for arm B")
    parser.add_argument("--output", type=Path, help="Markdown output path")
    parser.add_argument("--config-token-total-a", type=int, help="Optional config-level token total for arm A")
    parser.add_argument("--config-token-total-b", type=int, help="Optional config-level token total for arm B")
    args = parser.parse_args()

    main(
        raw_a=args.raw_a,
        raw_b=args.raw_b,
        name_a=args.name_a,
        name_b=args.name_b,
        output=args.output,
        config_token_total_a=args.config_token_total_a,
        config_token_total_b=args.config_token_total_b,
    )
