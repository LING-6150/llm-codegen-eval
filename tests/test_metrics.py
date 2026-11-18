from llm_codegen_eval.core.metrics import (
    DiagnosticSnapshot,
    PromptCharsMetricKey,
    RequestMetricKey,
    TokenMetricKey,
    diff_diagnostic_snapshots,
    diff_token_snapshots,
    extract_diagnostic_snapshot,
    extract_prompt_chars_counters,
    extract_request_counters,
    extract_token_counters,
    parse_prometheus_metrics,
    summarize_mechanism_delta,
    summarize_token_delta,
)


PROMETHEUS_TEXT_BEFORE = """
# HELP ai_model_tokens_total Total tokens used by AI model calls
# TYPE ai_model_tokens_total counter
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",token_type="input",user_id="user-1"} 100.0
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",token_type="output",user_id="user-1"} 20.0
ai_model_tokens_total{agent_name="ReviewAgent",app_id="app-1",model_name="zhipu-glm-4.5-flash",token_type="input",user_id="user-1"} 50.0
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-2",model_name="deepseek-v4-flash",token_type="input",user_id="user-1"} 999.0
ai_model_requests_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",status="started",user_id="user-1"} 2.0
ai_model_requests_total{agent_name="CodeGenAgent",app_id="app-2",model_name="deepseek-v4-flash",status="started",user_id="user-1"} 99.0
ai_agent_prompt_chars_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",user_id="user-1"} 1000.0
ai_agent_prompt_chars_total{agent_name="CodeGenAgent",app_id="app-2",model_name="deepseek-v4-flash",user_id="user-1"} 9999.0
"""

PROMETHEUS_TEXT_AFTER = """
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",token_type="input",user_id="user-1"} 175.0
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",token_type="output",user_id="user-1"} 45.0
ai_model_tokens_total{agent_name="ReviewAgent",app_id="app-1",model_name="zhipu-glm-4.5-flash",token_type="input",user_id="user-1"} 90.0
ai_model_tokens_total{agent_name="ReviewAgent",app_id="app-1",model_name="zhipu-glm-4.5-flash",token_type="output",user_id="user-1"} 10.0
ai_model_tokens_total{agent_name="CodeGenAgent",app_id="app-2",model_name="deepseek-v4-flash",token_type="input",user_id="user-1"} 1200.0
ai_model_requests_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",status="started",user_id="user-1"} 5.0
ai_model_requests_total{agent_name="ReviewAgent",app_id="app-1",model_name="zhipu-glm-4.5-flash",status="started",user_id="user-1"} 1.0
ai_model_requests_total{agent_name="CodeGenAgent",app_id="app-2",model_name="deepseek-v4-flash",status="started",user_id="user-1"} 120.0
ai_agent_prompt_chars_total{agent_name="CodeGenAgent",app_id="app-1",model_name="deepseek-v4-flash",user_id="user-1"} 2500.0
ai_agent_prompt_chars_total{agent_name="ReviewAgent",app_id="app-1",model_name="zhipu-glm-4.5-flash",user_id="user-1"} 700.0
ai_agent_prompt_chars_total{agent_name="CodeGenAgent",app_id="app-2",model_name="deepseek-v4-flash",user_id="user-1"} 12000.0
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


def test_request_and_prompt_char_counters_are_scoped_to_app_id():
    requests = extract_request_counters(PROMETHEUS_TEXT_AFTER, app_id="app-1")
    prompt_chars = extract_prompt_chars_counters(PROMETHEUS_TEXT_AFTER, app_id="app-1")

    assert requests[RequestMetricKey("CodeGenAgent", "deepseek-v4-flash", "started")] == 5.0
    assert requests[RequestMetricKey("ReviewAgent", "zhipu-glm-4.5-flash", "started")] == 1.0
    assert prompt_chars[PromptCharsMetricKey("CodeGenAgent", "deepseek-v4-flash")] == 2500.0
    assert PromptCharsMetricKey("CodeGenAgent", "deepseek-v4-flash") in prompt_chars
    assert all(key.model_name != "app-2" for key in prompt_chars)


def test_diagnostic_snapshot_diff_and_mechanism_summary():
    before = extract_diagnostic_snapshot(PROMETHEUS_TEXT_BEFORE, app_id="app-1")
    after = extract_diagnostic_snapshot(PROMETHEUS_TEXT_AFTER, app_id="app-1")

    assert isinstance(before, DiagnosticSnapshot)
    delta = diff_diagnostic_snapshots(before, after)
    summary = summarize_mechanism_delta(delta)

    codegen = summary["by_agent"]["CodeGenAgent"]
    assert codegen["requests_started"] == 3
    assert codegen["prompt_chars"] == 1500
    assert codegen["input_tokens"] == 75
    assert codegen["mean_prompt_chars_per_request"] == 500
    assert codegen["input_tokens_per_request"] == 25
