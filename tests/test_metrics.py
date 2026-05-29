from llm_codegen_eval.core.metrics import (
    TokenMetricKey,
    diff_token_snapshots,
    extract_token_counters,
    parse_prometheus_metrics,
    summarize_token_delta,
)


PROMETHEUS_TEXT_BEFORE = """
# HELP ai_model_tokens_total Total tokens used by AI model calls
# TYPE ai_model_tokens_total counter
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",token_type="input",user_id="user-1"} 100.0
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",token_type="output",user_id="user-1"} 20.0
ai_model_tokens_total{agent_name="ReviewAgent",app_id="app-1",model_name="zhipu-glm-4.5-flash",token_type="input",user_id="user-1"} 50.0
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-2",model_name="deepseek-v4-flash",token_type="input",user_id="user-1"} 999.0
"""

PROMETHEUS_TEXT_AFTER = """
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",token_type="input",user_id="user-1"} 175.0
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",token_type="output",user_id="user-1"} 45.0
ai_model_tokens_total{agent_name="ReviewAgent",app_id="app-1",model_name="zhipu-glm-4.5-flash",token_type="input",user_id="user-1"} 90.0
ai_model_tokens_total{agent_name="ReviewAgent",app_id="app-1",model_name="zhipu-glm-4.5-flash",token_type="output",user_id="user-1"} 10.0
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-2",model_name="deepseek-v4-flash",token_type="input",user_id="user-1"} 1200.0
"""


def test_parse_prometheus_metrics_extracts_name_labels_and_value():
    parsed = parse_prometheus_metrics(PROMETHEUS_TEXT_BEFORE)

    assert parsed[0][0] == "ai_model_tokens_total"
    assert parsed[0][1]["agent_name"] == "CodeGenAgent"
    assert parsed[0][1]["app_id"] == "app-1"
    assert parsed[0][2] == 100.0


def test_token_snapshot_diff_and_summary_are_scoped_to_app_id():
    before = extract_token_counters(PROMETHEUS_TEXT_BEFORE, app_id="app-1")
    after = extract_token_counters(PROMETHEUS_TEXT_AFTER, app_id="app-1")

    delta = diff_token_snapshots(before, after)
    summary = summarize_token_delta(delta)

    assert delta[TokenMetricKey("CodeGenAgent", "deepseek-v4-flash", "input")] == 75.0
    assert summary["input"] == 115
    assert summary["output"] == 35
    assert summary["total"] == 150
    assert summary["by_agent"]["CodeGenAgent"]["total"] == 100
    assert summary["by_agent"]["ReviewAgent"]["total"] == 50
