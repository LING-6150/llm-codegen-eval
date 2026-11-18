"""Helpers for capturing Java service Prometheus token counters."""

from collections import defaultdict
from dataclasses import dataclass
import re

import httpx


TOKEN_METRIC_NAME = "ai_model_tokens_total"
REQUEST_METRIC_NAME = "ai_model_requests_total"
PROMPT_CHARS_METRIC_NAME = "ai_agent_prompt_chars_total"


@dataclass(frozen=True)
class TokenMetricKey:
    agent_name: str
    model_name: str
    token_type: str


@dataclass(frozen=True)
class RequestMetricKey:
    agent_name: str
    model_name: str
    status: str


@dataclass(frozen=True)
class PromptCharsMetricKey:
    agent_name: str
    model_name: str


TokenSnapshot = dict[TokenMetricKey, float]
TokenSummary = dict[str, object]
RequestSnapshot = dict[RequestMetricKey, float]
PromptCharsSnapshot = dict[PromptCharsMetricKey, float]


@dataclass(frozen=True)
class DiagnosticSnapshot:
    tokens: TokenSnapshot
    requests: RequestSnapshot
    prompt_chars: PromptCharsSnapshot


async def fetch_prometheus_metrics(base_url: str) -> str:
    """Fetch the Java service Prometheus exposition text."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{base_url.rstrip('/')}/api/actuator/prometheus")
        response.raise_for_status()
        return response.text


def extract_token_counters(prometheus_text: str, app_id: str | None = None) -> TokenSnapshot:
    """Extract token counters, optionally scoped to one Java appId."""
    counters: TokenSnapshot = {}
    for metric_name, labels, value in parse_prometheus_metrics(prometheus_text):
        if metric_name != TOKEN_METRIC_NAME:
            continue
        if app_id is not None and labels.get("app_id") != app_id:
            continue
        token_type = labels.get("token_type")
        if token_type not in {"input", "output"}:
            continue
        key = TokenMetricKey(
            agent_name=labels.get("agent_name", "unknown"),
            model_name=labels.get("model_name", "unknown"),
            token_type=token_type,
        )
        counters[key] = counters.get(key, 0.0) + value
    return counters


def extract_request_counters(prometheus_text: str, app_id: str | None = None) -> RequestSnapshot:
    """Extract AI request counters, optionally scoped to one Java appId."""
    counters: RequestSnapshot = {}
    for metric_name, labels, value in parse_prometheus_metrics(prometheus_text):
        if metric_name != REQUEST_METRIC_NAME:
            continue
        if app_id is not None and labels.get("app_id") != app_id:
            continue
        status = labels.get("status")
        if not status:
            continue
        key = RequestMetricKey(
            agent_name=labels.get("agent_name", "unknown"),
            model_name=labels.get("model_name", "unknown"),
            status=status,
        )
        counters[key] = counters.get(key, 0.0) + value
    return counters


def extract_prompt_chars_counters(prometheus_text: str, app_id: str | None = None) -> PromptCharsSnapshot:
    """Extract outgoing prompt character counters, optionally scoped to one Java appId."""
    counters: PromptCharsSnapshot = {}
    for metric_name, labels, value in parse_prometheus_metrics(prometheus_text):
        if metric_name != PROMPT_CHARS_METRIC_NAME:
            continue
        if app_id is not None and labels.get("app_id") != app_id:
            continue
        key = PromptCharsMetricKey(
            agent_name=labels.get("agent_name", "unknown"),
            model_name=labels.get("model_name", "unknown"),
        )
        counters[key] = counters.get(key, 0.0) + value
    return counters


def extract_diagnostic_snapshot(prometheus_text: str, app_id: str | None = None) -> DiagnosticSnapshot:
    """Extract all eval diagnostic counters from one Prometheus scrape."""
    return DiagnosticSnapshot(
        tokens=extract_token_counters(prometheus_text, app_id=app_id),
        requests=extract_request_counters(prometheus_text, app_id=app_id),
        prompt_chars=extract_prompt_chars_counters(prometheus_text, app_id=app_id),
    )


def diff_token_snapshots(before: TokenSnapshot, after: TokenSnapshot) -> TokenSnapshot:
    """Return positive counter deltas between two snapshots."""
    diff: TokenSnapshot = {}
    for key, after_value in after.items():
        delta = after_value - before.get(key, 0.0)
        if delta > 0:
            diff[key] = delta
    return diff


def diff_request_snapshots(before: RequestSnapshot, after: RequestSnapshot) -> RequestSnapshot:
    """Return positive request counter deltas between two snapshots."""
    return _diff_positive(before, after)


def diff_prompt_chars_snapshots(
    before: PromptCharsSnapshot,
    after: PromptCharsSnapshot,
) -> PromptCharsSnapshot:
    """Return positive prompt character counter deltas between two snapshots."""
    return _diff_positive(before, after)


def diff_diagnostic_snapshots(
    before: DiagnosticSnapshot,
    after: DiagnosticSnapshot,
) -> DiagnosticSnapshot:
    """Return positive deltas for all diagnostic counters."""
    return DiagnosticSnapshot(
        tokens=diff_token_snapshots(before.tokens, after.tokens),
        requests=diff_request_snapshots(before.requests, after.requests),
        prompt_chars=diff_prompt_chars_snapshots(before.prompt_chars, after.prompt_chars),
    )


def summarize_token_delta(delta: TokenSnapshot) -> TokenSummary:
    """Summarize token deltas by token type and agent."""
    by_type = {"input": 0.0, "output": 0.0}
    by_agent: dict[str, dict[str, float]] = defaultdict(lambda: {"input": 0.0, "output": 0.0, "total": 0.0})
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: {"input": 0.0, "output": 0.0, "total": 0.0})

    for key, value in delta.items():
        by_type[key.token_type] = by_type.get(key.token_type, 0.0) + value
        by_agent[key.agent_name][key.token_type] += value
        by_agent[key.agent_name]["total"] += value
        by_model[key.model_name][key.token_type] += value
        by_model[key.model_name]["total"] += value

    total = by_type.get("input", 0.0) + by_type.get("output", 0.0)
    return {
        "input": int(round(by_type.get("input", 0.0))),
        "output": int(round(by_type.get("output", 0.0))),
        "total": int(round(total)),
        "by_agent": _round_nested(by_agent),
        "by_model": _round_nested(by_model),
    }


def summarize_mechanism_delta(delta: DiagnosticSnapshot) -> dict[str, object]:
    """Summarize model-request and prompt-size diagnostics by agent."""
    agents = sorted(
        {key.agent_name for key in delta.tokens}
        | {key.agent_name for key in delta.requests}
        | {key.agent_name for key in delta.prompt_chars}
    )
    by_agent = {}
    for agent in agents:
        requests_started = sum(
            value
            for key, value in delta.requests.items()
            if key.agent_name == agent and key.status == "started"
        )
        prompt_chars = sum(
            value
            for key, value in delta.prompt_chars.items()
            if key.agent_name == agent
        )
        input_tokens = sum(
            value
            for key, value in delta.tokens.items()
            if key.agent_name == agent and key.token_type == "input"
        )
        by_agent[agent] = {
            "requests_started": int(round(requests_started)),
            "prompt_chars": int(round(prompt_chars)),
            "input_tokens": int(round(input_tokens)),
            "mean_prompt_chars_per_request": _safe_ratio(prompt_chars, requests_started),
            "input_tokens_per_request": _safe_ratio(input_tokens, requests_started),
        }
    return {"by_agent": by_agent}


def parse_prometheus_metrics(prometheus_text: str) -> list[tuple[str, dict[str, str], float]]:
    """Parse a small Prometheus text subset into metric name, labels, value."""
    parsed = []
    for raw_line in prometheus_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([-+0-9.eE]+)$", line)
        if not match:
            continue

        metric_name, raw_labels, raw_value = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            continue

        parsed.append((metric_name, _parse_labels(raw_labels or ""), value))
    return parsed


def _parse_labels(raw_labels: str) -> dict[str, str]:
    labels = {}
    for match in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"', raw_labels):
        labels[match.group(1)] = match.group(2).replace(r"\"", '"').replace(r"\\", "\\")
    return labels


def _round_nested(values: dict[str, dict[str, float]]) -> dict[str, dict[str, int]]:
    return {
        key: {inner_key: int(round(inner_value)) for inner_key, inner_value in inner.items()}
        for key, inner in sorted(values.items())
    }


def _diff_positive(before: dict, after: dict) -> dict:
    diff = {}
    for key, after_value in after.items():
        delta = after_value - before.get(key, 0.0)
        if delta > 0:
            diff[key] = delta
    return diff


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
