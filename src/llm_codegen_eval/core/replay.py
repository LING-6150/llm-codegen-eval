"""Offline replay helpers for saved eval artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .case import CodeType, EvalCase
from .result import EvalResult
from .results_io import TRUNCATION_MARKER, load_results
from .reporter import generate_markdown
from ..evaluators.base import BaseEvaluator
from ..evaluators.html_eval import HtmlEvaluator
from ..evaluators.vue_eval import VueEvaluator
from ..evaluators.execution_smoke import evaluate_execution_smoke


REPLAY_BANNER = (
    "REPLAY REPORT - re-rendered from saved raw results, not a live benchmark run."
)

_EVALUATORS: dict[CodeType, type[BaseEvaluator]] = {
    CodeType.HTML: HtmlEvaluator,
    CodeType.MULTI_FILE: HtmlEvaluator,
    CodeType.VUE_PROJECT: VueEvaluator,
}


@dataclass(frozen=True)
class ReplayArtifact:
    """Complete generated artifact used for offline evaluator replay."""

    case_id: str
    code_type: CodeType
    generated_code: str
    expected_structural_passed: bool | None = None
    expected_execution_smoke_passed: bool | None = None


def replay_report_markdown(
    raw_path: Path,
    cases: list[EvalCase],
    config_name: str = "replay",
) -> str:
    """Re-render a saved raw JSON result file without live-run dependencies."""
    results = load_results(raw_path)
    result_case_ids = {r.case_id for r in results}
    selected_cases = [case for case in cases if case.case_id in result_case_ids]

    return generate_markdown(
        results,
        selected_cases,
        config_name=config_name,
        config_details={
            "Replay mode": "report-only",
            "Raw source": str(raw_path),
            "Live Java calls": "False",
            "Provider calls": "False",
            "Memory cleanup": "not applicable",
            "Token capture": "from saved raw only",
        },
        top_banner=REPLAY_BANNER,
    )


def load_replay_artifacts(fixtures_path: Path) -> list[ReplayArtifact]:
    """Load complete generated-code fixtures from a JSON file or directory."""
    paths = (
        sorted(fixtures_path.glob("*.json"))
        if fixtures_path.is_dir()
        else [fixtures_path]
    )
    artifacts: list[ReplayArtifact] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        for item in items:
            artifacts.append(_artifact_from_dict(item, source=path))
    return artifacts


async def replay_artifacts(
    artifacts: list[ReplayArtifact],
    cases: list[EvalCase],
    execution_smoke: bool = False,
) -> list[EvalResult]:
    """Re-run structural evaluators over complete saved artifacts."""
    case_map = {case.case_id: case for case in cases}
    results: list[EvalResult] = []
    for artifact in artifacts:
        case = case_map.get(artifact.case_id)
        if case is None:
            raise ValueError(f"Replay artifact references unknown case_id: {artifact.case_id}")
        if artifact.code_type != case.code_type:
            raise ValueError(
                f"Replay artifact {artifact.case_id} code_type={artifact.code_type.value} "
                f"does not match case code_type={case.code_type.value}"
            )
        _assert_complete_generated_code(artifact.generated_code, context=artifact.case_id)
        evaluator = _EVALUATORS[case.code_type]()
        result = await evaluator.evaluate(artifact.generated_code, case)
        if execution_smoke:
            result.execution_smoke = await evaluate_execution_smoke(
                artifact.generated_code,
                case,
            )
        result.run_config.update({
            "replay_mode": "artifact-fixture",
            "live_java_calls": False,
            "provider_calls": False,
            "execution_smoke": execution_smoke,
        })
        results.append(result)
    return results


def assert_replayable_generated_code(result: EvalResult) -> None:
    """Raise when a raw result cannot be safely re-evaluated offline."""
    if result.generated_code_truncated:
        raise ValueError(
            f"{result.case_id} generated_code is truncated; evaluator replay requires "
            "a complete artifact or sidecar file"
        )
    _assert_complete_generated_code(result.generated_code, context=result.case_id)


def _artifact_from_dict(item: dict, source: Path) -> ReplayArtifact:
    try:
        code_type = CodeType(item["code_type"])
        generated_code = item["generated_code"]
        case_id = item["case_id"]
    except KeyError as exc:
        raise ValueError(f"Replay fixture {source} missing required field: {exc}") from exc

    _assert_complete_generated_code(generated_code, context=f"{source}:{case_id}")
    return ReplayArtifact(
        case_id=case_id,
        code_type=code_type,
        generated_code=generated_code,
        expected_structural_passed=item.get("expected_structural_passed"),
        expected_execution_smoke_passed=item.get("expected_execution_smoke_passed"),
    )


def _assert_complete_generated_code(generated_code: str, context: str) -> None:
    if not generated_code:
        raise ValueError(f"{context} has no generated_code for replay")
    if generated_code.endswith(TRUNCATION_MARKER):
        raise ValueError(f"{context} generated_code is truncated and cannot be replayed")
