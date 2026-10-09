import json
import pytest
from llm_codegen_eval.training.data import prepare, verify, prompt_key
from llm_codegen_eval.training.train import conversational

@pytest.fixture
def source(tmp_path):
    path = tmp_path/"source.jsonl"
    path.write_text("".join(json.dumps({"prompt": f"Question {i}", "completion": "<h1>Answer</h1>"})+"\n" for i in range(10)))
    benchmark = tmp_path/"cases.json"; benchmark.write_text('[{"prompt": "Held out"}]')
    return path, benchmark


def test_split_is_reproducible_and_detects_tampering(source, tmp_path):
    first = prepare(*source, tmp_path/"a")
    second = prepare(*source, tmp_path/"b")
    assert first == second
    assert first["train_rows"] == 8 and first["validation_rows"] == 2
    assert verify(tmp_path/"a") == first
    train = [json.loads(l)["prompt"] for l in (tmp_path/"a/train.jsonl").read_text().splitlines()]
    val = [json.loads(l)["prompt"] for l in (tmp_path/"a/validation.jsonl").read_text().splitlines()]
    assert not set(train) & set(val)
    (tmp_path/"a/train.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        verify(tmp_path/"a")

@pytest.mark.parametrize("bad", ["held   OUT", "Question 1"])
def test_leakage_and_duplicate_prompts_rejected(source, tmp_path, bad):
    path, benchmark = source
    with path.open("a") as f:
        f.write(json.dumps({"prompt": bad, "completion": "answer"})+"\n")
    with pytest.raises(ValueError):
        prepare(path, benchmark, tmp_path/"split")


def test_chat_format_keeps_completion_out_of_prompt():
    row = conversational({"prompt": "Make HTML", "completion": "<h1>Only answer</h1>"})
    assert row["completion"][0]["role"] == "assistant"
    assert all("Only answer" not in m["content"] for m in row["prompt"])
    assert prompt_key(" HELLO \n WORLD ") == "hello world"
