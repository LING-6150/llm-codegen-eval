"""Replay complete generated-code fixtures through offline evaluators."""

import argparse
import asyncio
from pathlib import Path

from llm_codegen_eval.core.cases_io import load_cases
from llm_codegen_eval.core.replay import load_replay_artifacts, replay_artifacts
from llm_codegen_eval.core.reporter import generate_markdown, save_report


CASES_PATH = Path("src/llm_codegen_eval/benchmarks/cases.json")


async def main(
    fixtures: Path,
    cases_path: Path = CASES_PATH,
    name: str = "replay_artifacts",
    output_prefix: str | None = None,
    execution_smoke: bool = False,
) -> Path:
    cases = load_cases(cases_path)
    artifacts = load_replay_artifacts(fixtures)
    results = await replay_artifacts(artifacts, cases, execution_smoke=execution_smoke)
    report = generate_markdown(
        results,
        cases,
        config_name=name,
        config_details={
            "Replay mode": "artifact-fixture",
            "Fixture source": str(fixtures),
            "Live Java calls": "False",
            "Provider calls": "False",
            "Memory cleanup": "not applicable",
            "Token capture": "not applicable",
            "Execution smoke replay": str(execution_smoke),
        },
        top_banner="REPLAY REPORT - evaluator replay from complete saved artifacts, not a live benchmark run.",
    )
    report_path = save_report(report, filename_prefix=output_prefix or name)
    print(f"Artifact replay report saved to: {report_path}")
    return report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Replay complete generated-code fixtures through offline evaluators"
    )
    parser.add_argument("--fixtures", type=Path, required=True, help="Fixture JSON file or directory")
    parser.add_argument("--cases", type=Path, default=CASES_PATH, help="Benchmark cases JSON")
    parser.add_argument("--name", default="replay_artifacts", help="Replay report display name")
    parser.add_argument("--output-prefix", help="Report filename prefix")
    parser.add_argument("--execution-smoke", action="store_true", help="Replay execution smoke checks")
    args = parser.parse_args()

    asyncio.run(
        main(
            fixtures=args.fixtures,
            cases_path=args.cases,
            name=args.name,
            output_prefix=args.output_prefix,
            execution_smoke=args.execution_smoke,
        )
    )
