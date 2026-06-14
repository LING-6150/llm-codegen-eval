"""Replay a saved raw result JSON into a markdown report without live calls."""

import argparse
from pathlib import Path

from llm_codegen_eval.core.cases_io import load_cases
from llm_codegen_eval.core.replay import replay_report_markdown
from llm_codegen_eval.core.reporter import save_report


CASES_PATH = Path("src/llm_codegen_eval/benchmarks/cases.json")


def main(
    raw: Path,
    cases_path: Path = CASES_PATH,
    name: str = "replay_report",
    output_prefix: str | None = None,
) -> Path:
    cases = load_cases(cases_path)
    report = replay_report_markdown(raw, cases, config_name=name)
    report_path = save_report(report, filename_prefix=output_prefix or name)
    print(f"Replay report saved to: {report_path}")
    return report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-render a saved raw result JSON without live Java/provider calls"
    )
    parser.add_argument("--raw", type=Path, required=True, help="Saved raw JSON results")
    parser.add_argument("--cases", type=Path, default=CASES_PATH, help="Benchmark cases JSON")
    parser.add_argument("--name", default="replay_report", help="Replay report display name")
    parser.add_argument("--output-prefix", help="Report filename prefix")
    args = parser.parse_args()

    main(
        raw=args.raw,
        cases_path=args.cases,
        name=args.name,
        output_prefix=args.output_prefix,
    )
