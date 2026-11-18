import pytest

from llm_codegen_eval.core.batch_runner import run_batch
from llm_codegen_eval.core.case import CodeType, Difficulty, ElementCheck, EvalCase
from llm_codegen_eval.core.reporter import generate_markdown
from llm_codegen_eval.evaluators.execution_smoke import evaluate_execution_smoke


class RepairPathFakeClient:
    def __init__(self):
        self.base_url = "http://fake-java"
        self.app_id = "app_1"
        self.prompts: list[str] = []

    async def login(self):
        return None

    async def health(self):
        return True

    async def generate(self, prompt: str, agent: bool = True, extra_params=None):
        self.prompts.append(prompt)
        code = _bad_first_shot_html() if len(self.prompts) == 1 else _repaired_html()
        return {
            "code": code,
            "review_score": None,
            "review_passed": None,
            "duration_ms": 10,
            "error": None,
        }


def repair_case() -> EvalCase:
    return EvalCase(
        case_id="repair_fixture",
        prompt="Create a small dashboard with a heading and two cards.",
        code_type=CodeType.HTML,
        difficulty=Difficulty.EASY,
        required_checks=[
            ElementCheck(type="tag_exists", selector="h1", description="Heading"),
            ElementCheck(type="tag_count", selector=".card", expected=2, description="Cards"),
        ],
    )


def _bad_first_shot_html() -> str:
    return """
    <!doctype html>
    <html>
      <body>
        <h1>Dashboard</h1>
        <div class="card">A</div>
        <div class="card">B</div>
        <script>console.error("fixture repair needed")</script>
      </body>
    </html>
    """


def _repaired_html() -> str:
    return """
    <!doctype html>
    <html>
      <body>
        <h1>Dashboard</h1>
        <div class="card">A</div>
        <div class="card">B</div>
      </body>
    </html>
    """


async def _require_real_browser():
    result = await evaluate_execution_smoke(_repaired_html(), repair_case())
    if result.failure_type == "checker_error" and result.detail and (
        "Executable doesn't exist" in result.detail
        or "playwright install" in result.detail
        or "BrowserType.launch" in result.detail
    ):
        pytest.skip(f"Playwright browser is not installed: {result.detail.splitlines()[0]}")
    assert result.passed is True


@pytest.mark.asyncio
async def test_repair_path_runs_through_batch_and_report_with_real_browser():
    await _require_real_browser()

    client = RepairPathFakeClient()
    case = repair_case()

    results = await run_batch(
        [case],
        client,
        execution_smoke=True,
        repair_on_execution_fail=True,
        health_check=False,
    )

    assert len(client.prompts) == 2
    assert results[0].passed is True
    assert results[0].score == 100
    assert results[0].execution_smoke is not None
    assert results[0].execution_smoke.passed is False
    assert results[0].execution_smoke.failure_type == "console_error"

    repair = results[0].repair_summary
    assert repair is not None
    assert repair.attempted is True
    assert repair.succeeded is True
    assert repair.trigger_failure_type == "console_error"
    assert repair.repaired_structural_passed is True
    assert repair.repaired_score == 100
    assert repair.repaired_execution_smoke is not None
    assert repair.repaired_execution_smoke.passed is True

    report = generate_markdown(results, [case], config_name="repair_fixture")

    assert "- **Execution smoke pass rate**: 0.0% (0/1 judged runs)" in report
    assert "- **Pass after one repair (includes one repair)**: 100.0% (1/1)" in report
    assert "- **Repair uplift**: +100.0 pp (pass_after_one_repair - first_shot_execution_pass)" in report
    assert "- **Repair attempts/successes**: 1/1" in report
    assert "- **Repair generation errors**: 0" in report
    assert "- **Repair token cost**: 0" in report
    assert "| repair_fixture | 1 | 0/1 | 1 | 1 | 0 | 1/1 | 0 | repair_succeeded |" in report
