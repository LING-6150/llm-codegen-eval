import pytest

from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase, ElementCheck
from llm_codegen_eval.core.runner import run_case


class FakeClient:
    def __init__(self):
        self.agent_values = []
        self.extra_params_values = []

    async def generate(self, prompt: str, agent: bool = True, extra_params=None):
        self.agent_values.append(agent)
        self.extra_params_values.append(extra_params)
        return {
            "code": "<html><body><h1>Hello</h1></body></html>",
            "review_score": 90,
            "review_passed": True,
            "duration_ms": 123,
            "error": None,
        }


@pytest.mark.asyncio
async def test_run_case_passes_agent_flag_to_client():
    case = EvalCase(
        case_id="html_fake",
        prompt="Create hello page",
        code_type=CodeType.HTML,
        difficulty=Difficulty.EASY,
        required_checks=[
            ElementCheck(type="tag_exists", selector="h1", description="Heading")
        ],
    )
    client = FakeClient()

    result = await run_case(case, client, agent=False, java_params={"contextPruning": True})

    assert client.agent_values == [False]
    assert client.extra_params_values == [{"contextPruning": True}]
    assert result.passed is True
    assert result.run_config["agent"] is False
    assert result.run_config["java_params"] == {"contextPruning": True}
