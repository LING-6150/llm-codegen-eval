"""Run a single eval case against the Java service."""

from pathlib import Path

from .case import EvalCase, CodeType
from .result import EvalResult, FinalArtifactResult, RepairSummary
from ..clients.java_client import JavaServiceClient
from ..evaluators.html_eval import HtmlEvaluator
from ..evaluators.vue_eval import VueEvaluator
from ..evaluators.base import BaseEvaluator
from ..evaluators.execution_smoke import evaluate_execution_smoke

_EVALUATORS: dict[CodeType, type[BaseEvaluator]] = {
    CodeType.HTML: HtmlEvaluator,
    CodeType.MULTI_FILE: HtmlEvaluator,  # TODO: dedicated MultiFileEvaluator (Day 4)
    CodeType.VUE_PROJECT: VueEvaluator,
}

REPAIRABLE_EXECUTION_FAILURES = {
    "load_failure",
    "console_error",
    "missing_element",
    "build_failure",
}

# v2 keeps case-specific selectors out of the generation prompt.
REPAIR_PROMPT_VERSION = 2

async def run_case(
    case: EvalCase,
    client: JavaServiceClient,
    agent: bool = True,
    java_params: dict | None = None,
    execution_smoke: bool = False,
    score_final_artifact: bool = False,
    final_artifact_dir: Path | None = None,
) -> EvalResult:
    baseline_hash = await _snapshot_artifact_hash(client) if score_final_artifact else None

    try:
        gen_result = await client.generate(case.prompt, agent=agent, extra_params=java_params)
    except Exception as e:
        return EvalResult(
            case_id=case.case_id,
            passed=False,
            score=0,
            required_passed=0,
            required_total=len(case.required_checks),
            optional_passed=0,
            optional_total=len(case.optional_checks),
            error=f"Generation failed: {e}",
            run_config={"agent": agent, "java_params": java_params or {}},
        )

    if gen_result.get("error"):
        return EvalResult(
            case_id=case.case_id,
            passed=False,
            score=0,
            required_passed=0,
            required_total=len(case.required_checks),
            optional_passed=0,
            optional_total=len(case.optional_checks),
            generation_duration_ms=gen_result["duration_ms"],
            error=f"Workflow error: {gen_result['error']}",
            run_config={"agent": agent, "java_params": java_params or {}},
        )

    if (
        not gen_result.get("code", "").strip()
        and not gen_result.get("error")
        and gen_result.get("duration_ms", 0) < 1000
    ):
        return EvalResult(
            case_id=case.case_id,
            passed=False,
            score=0,
            required_passed=0,
            required_total=len(case.required_checks),
            optional_passed=0,
            optional_total=len(case.optional_checks),
            generation_duration_ms=gen_result["duration_ms"],
            error="Infra error: empty response from Java service",
            run_config={"agent": agent, "java_params": java_params or {}},
        )

    result = await _evaluate_generated_code(gen_result["code"], case)
    if execution_smoke:
        result.execution_smoke = await evaluate_execution_smoke(gen_result["code"], case)

    result.generation_duration_ms = gen_result["duration_ms"]
    result.review_score = gen_result.get("review_score")
    result.review_passed = gen_result.get("review_passed")
    result.run_config.update({"agent": agent, "java_params": java_params or {}})

    if score_final_artifact:
        result.final_artifact = await _score_final_artifact(
            client,
            case,
            generated_type=gen_result.get("code_gen_type"),
            baseline_hash=baseline_hash,
            execution_smoke=execution_smoke,
            artifact_dir=final_artifact_dir,
        )

    return result


async def _snapshot_artifact_hash(client: JavaServiceClient) -> str | None:
    """Hash of the output directory before generation, to detect stale downloads."""
    from .final_artifact import content_hash, extract_zip_files

    try:
        return content_hash(extract_zip_files(await client.download_artifact()))
    except Exception:
        return None


async def _score_final_artifact(
    client: JavaServiceClient,
    case: EvalCase,
    generated_type: str | None,
    baseline_hash: str | None,
    execution_smoke: bool,
    artifact_dir: Path | None,
) -> FinalArtifactResult:
    """Score the post-Review/Refine files; never fails the run itself."""
    from .final_artifact import content_hash, evaluate_final_artifact, extract_zip_files

    try:
        app_type = await client.get_app_code_gen_type()
        if generated_type and app_type and generated_type != app_type:
            # The download endpoint zips {appType}_{appId}; the orchestrator wrote
            # {generatedType}_{appId}. Scoring the download would read another run's files.
            return FinalArtifactResult(
                available=False,
                generated_code_gen_type=generated_type,
                error=(
                    f"Generated type {generated_type} differs from app type {app_type}; "
                    "download would serve a different directory"
                ),
            )

        files = extract_zip_files(await client.download_artifact())
        if baseline_hash is not None and content_hash(files) == baseline_hash:
            return FinalArtifactResult(
                available=False,
                generated_code_gen_type=generated_type,
                error="Output directory unchanged since before the run; files may be stale",
            )

        result = await evaluate_final_artifact(
            files,
            case,
            execution_smoke=execution_smoke,
            artifact_dir=artifact_dir,
        )
        result.generated_code_gen_type = generated_type
        return result
    except Exception as exc:
        return FinalArtifactResult(
            available=False,
            generated_code_gen_type=generated_type,
            error=f"Final artifact unavailable: {exc}",
        )


async def run_repair(
    first_shot: EvalResult,
    case: EvalCase,
    client: JavaServiceClient,
    agent: bool = True,
    java_params: dict | None = None,
) -> RepairSummary:
    """Attempt exactly one repair using deterministic execution-smoke feedback."""

    if not should_attempt_repair(first_shot):
        return RepairSummary(
            attempted=False,
            succeeded=False,
            trigger_failure_type=(
                first_shot.execution_smoke.failure_type
                if first_shot.execution_smoke is not None
                else None
            ),
            reason=_repair_skip_reason(first_shot),
        )

    assert first_shot.execution_smoke is not None
    trigger_failure_type = first_shot.execution_smoke.failure_type
    repair_prompt = _build_repair_prompt(case, first_shot)

    try:
        gen_result = await client.generate(repair_prompt, agent=agent, extra_params=java_params)
    except Exception as exc:
        return RepairSummary(
            attempted=True,
            succeeded=False,
            trigger_failure_type=trigger_failure_type,
            reason="repair_generation_error",
            error=f"Repair generation failed: {exc}",
        )

    if gen_result.get("error"):
        return RepairSummary(
            attempted=True,
            succeeded=False,
            trigger_failure_type=trigger_failure_type,
            reason="repair_generation_error",
            error=f"Repair workflow error: {gen_result['error']}",
        )

    if (
        not gen_result.get("code", "").strip()
        and not gen_result.get("error")
        and gen_result.get("duration_ms", 0) < 1000
    ):
        return RepairSummary(
            attempted=True,
            succeeded=False,
            trigger_failure_type=trigger_failure_type,
            reason="repair_generation_error",
            error="Repair infra error: empty response from Java service",
        )

    repaired_result = await _evaluate_generated_code(gen_result["code"], case)
    repaired_smoke = await evaluate_execution_smoke(gen_result["code"], case)
    succeeded = repaired_result.passed and repaired_smoke.applicable and repaired_smoke.passed
    return RepairSummary(
        attempted=True,
        succeeded=succeeded,
        trigger_failure_type=trigger_failure_type,
        reason="repair_succeeded" if succeeded else "repaired_still_failing",
        repaired_structural_passed=repaired_result.passed,
        repaired_score=repaired_result.score,
        repaired_execution_smoke=repaired_smoke,
        prompt_version=REPAIR_PROMPT_VERSION,
    )


def should_attempt_repair(result: EvalResult) -> bool:
    """Return True only for whitelisted first-shot app-level smoke failures."""

    smoke = result.execution_smoke
    if result.error or smoke is None or not smoke.applicable or smoke.passed:
        return False
    return smoke.failure_type in REPAIRABLE_EXECUTION_FAILURES


async def _evaluate_generated_code(code: str, case: EvalCase) -> EvalResult:
    evaluator_cls = _EVALUATORS.get(case.code_type)
    if not evaluator_cls:
        raise ValueError(f"No evaluator for {case.code_type}")

    evaluator = evaluator_cls()
    return await evaluator.evaluate(code, case)


def _repair_skip_reason(result: EvalResult) -> str:
    if result.error:
        return "first_shot_error"
    if result.execution_smoke is None:
        return "execution_smoke_missing"
    if not result.execution_smoke.applicable:
        return "execution_smoke_not_applicable"
    if result.execution_smoke.passed:
        return "execution_smoke_passed"
    if result.execution_smoke.failure_type not in REPAIRABLE_EXECUTION_FAILURES:
        return "not_whitelisted"
    return "repair_not_attempted"


def _build_repair_prompt(case: EvalCase, result: EvalResult) -> str:
    smoke = result.execution_smoke
    failure_type = smoke.failure_type if smoke else "unknown"
    detail = smoke.detail if smoke and smoke.detail else ""
    if failure_type == "missing_element":
        # The raw detail lists the case's hidden selectors; feeding them back would
        # let the generator target the judge instead of the user request.
        detail = "Some page elements the request needs were not present after load."
    generated_code = result.generated_code[:20000]
    return (
        "Repair the generated code for the same user request.\n\n"
        "Original request:\n"
        f"{case.prompt}\n\n"
        "Execution smoke failure:\n"
        f"- failure_type: {failure_type}\n"
        f"- detail: {detail[:4000]}\n\n"
        "Current generated code:\n"
        f"{generated_code}\n\n"
        "Return a complete corrected version of the generated artifact. "
        "Do not explain the fix; output only the code/files in the same format as the original generation."
    )
