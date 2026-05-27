"""Run a single eval case against the Java service."""

from .case import EvalCase, CodeType
from .result import EvalResult
from ..clients.java_client import JavaServiceClient
from ..evaluators.html_eval import HtmlEvaluator
from ..evaluators.base import BaseEvaluator

_EVALUATORS: dict[CodeType, type[BaseEvaluator]] = {
    CodeType.HTML: HtmlEvaluator,
    CodeType.MULTI_FILE: HtmlEvaluator,  # TODO: dedicated MultiFileEvaluator (Day 4)
    CodeType.VUE_PROJECT: HtmlEvaluator,  # TODO: dedicated VueEvaluator (Day 4)
}

async def run_case(case: EvalCase, client: JavaServiceClient) -> EvalResult:
    try:
        gen_result = await client.generate(case.prompt, agent=True)
    except Exception as e:
        return EvalResult(
            case_id=case.case_id,
            passed=False,
            score=0,
            required_passed=0,
            required_total=len(case.required_checks),
            optional_passed=0,
            optional_total=len(case.optional_checks),
            error=f"Generation failed: {e}"
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
            error=f"Workflow error: {gen_result['error']}"
        )

    evaluator_cls = _EVALUATORS.get(case.code_type)
    if not evaluator_cls:
        raise ValueError(f"No evaluator for {case.code_type}")

    evaluator = evaluator_cls()
    result = await evaluator.evaluate(gen_result["code"], case)

    result.generation_duration_ms = gen_result["duration_ms"]
    result.review_score = gen_result.get("review_score")
    result.review_passed = gen_result.get("review_passed")

    return result
