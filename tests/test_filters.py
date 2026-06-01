import pytest

from llm_codegen_eval.core.case import CodeType, Difficulty, EvalCase
from llm_codegen_eval.core.filters import filter_cases_by_id, parse_case_ids


def make_case(case_id: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        prompt="Create a page",
        code_type=CodeType.HTML,
        difficulty=Difficulty.EASY,
        required_checks=[],
    )


def test_parse_case_ids_handles_commas_and_spaces():
    assert parse_case_ids("multi_018, multi_019,,multi_020") == [
        "multi_018",
        "multi_019",
        "multi_020",
    ]


def test_filter_cases_by_id_preserves_requested_order():
    cases = [make_case("multi_018"), make_case("multi_019"), make_case("multi_020")]

    selected = filter_cases_by_id(cases, ["multi_020", "multi_018"])

    assert [case.case_id for case in selected] == ["multi_020", "multi_018"]


def test_filter_cases_by_id_rejects_unknown_case_id():
    with pytest.raises(ValueError, match="Unknown case id"):
        filter_cases_by_id([make_case("multi_018")], ["multi_999"])
