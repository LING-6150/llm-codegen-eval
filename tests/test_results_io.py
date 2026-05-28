from pathlib import Path

from llm_codegen_eval.core.batch_runner import load_results, save_results
from llm_codegen_eval.core.result import EvalResult


def test_save_and_load_results_round_trip(tmp_path: Path):
    path = tmp_path / "raw.json"
    results = [
        EvalResult(
            case_id="case_a",
            passed=True,
            score=100,
            required_passed=1,
            required_total=1,
            optional_passed=0,
            optional_total=0,
            run_config={"run_index": 1},
        )
    ]

    save_results(results, path)
    loaded = load_results(path)

    assert len(loaded) == 1
    assert loaded[0].case_id == "case_a"
    assert loaded[0].passed is True
    assert loaded[0].run_config["run_index"] == 1
