"""Generate an A/B report from previously saved raw result JSON files."""

import argparse
from pathlib import Path

from llm_codegen_eval.core.cases_io import load_cases
from llm_codegen_eval.core.config import load_run_config
from llm_codegen_eval.core.reporter import generate_ab_report, save_report
from llm_codegen_eval.core.results_io import load_results

CASES_PATH = Path("src/llm_codegen_eval/benchmarks/cases.json")


def main(
    raw_a: Path,
    raw_b: Path,
    config_a_path: Path,
    config_b_path: Path,
    filter_type: str | None = None,
    output_prefix: str | None = None,
):
    config_a = load_run_config(config_a_path)
    config_b = load_run_config(config_b_path)
    cases = load_cases(CASES_PATH)
    if filter_type:
        cases = [c for c in cases if c.code_type.value == filter_type]

    results_a = load_results(raw_a)
    results_b = load_results(raw_b)
    selected_case_ids = {c.case_id for c in cases}
    results_a = [r for r in results_a if r.case_id in selected_case_ids]
    results_b = [r for r in results_b if r.case_id in selected_case_ids]
    result_case_ids = {r.case_id for r in results_a} | {r.case_id for r in results_b}
    cases = [c for c in cases if c.case_id in result_case_ids]

    report = generate_ab_report(
        results_a,
        results_b,
        cases,
        config_a.name,
        config_b.name,
        config_details={
            "Raw A": str(raw_a),
            "Raw B": str(raw_b),
            "Config A java_service": config_a.java_service or "-",
            "Config B java_service": config_b.java_service or "-",
        },
    )
    prefix = output_prefix or f"ab_compare_{config_a.name}_vs_{config_b.name}"
    report_path = save_report(report, filename_prefix=prefix)
    print(f"A/B report saved to: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate A/B report from raw result JSON")
    parser.add_argument("--raw-a", type=Path, required=True, help="Raw JSON results for config A")
    parser.add_argument("--raw-b", type=Path, required=True, help="Raw JSON results for config B")
    parser.add_argument("--config-a", type=Path, required=True, help="YAML config for variant A")
    parser.add_argument("--config-b", type=Path, required=True, help="YAML config for variant B")
    parser.add_argument("--type", choices=["html", "multi_file", "vue_project"], help="Filter by code type")
    parser.add_argument("--output-prefix", help="Report filename prefix")
    args = parser.parse_args()

    main(
        raw_a=args.raw_a,
        raw_b=args.raw_b,
        config_a_path=args.config_a,
        config_b_path=args.config_b,
        filter_type=args.type,
        output_prefix=args.output_prefix,
    )
