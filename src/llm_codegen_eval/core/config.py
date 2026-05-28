"""Benchmark run configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GenerationConfig:
    agent: bool = True


@dataclass(frozen=True)
class EvalRunConfig:
    name: str
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    java_service: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConfigError(ValueError):
    """Raised when an eval run config cannot be loaded."""


def java_request_params(config: EvalRunConfig) -> dict[str, Any]:
    """Convert java_service.params config keys to Java HTTP request params."""
    params = config.java_service.get("params", {})
    if not isinstance(params, dict):
        raise ConfigError("java_service.params must be a mapping")

    request_params: dict[str, Any] = {}
    for key, value in params.items():
        if key == "context.pruning.enabled":
            request_params["contextPruning"] = value
        elif key == "agent.orchestrator.enabled":
            continue
        else:
            request_params[key] = value
    return request_params


def load_run_config(path: Path) -> EvalRunConfig:
    data = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"Config must be a mapping: {path}")

    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigError(f"Config must define a non-empty name: {path}")

    generation_data = data.get("generation", {})
    if generation_data is None:
        generation_data = {}
    if not isinstance(generation_data, dict):
        raise ConfigError("generation must be a mapping")

    agent = generation_data.get("agent", True)
    if not isinstance(agent, bool):
        raise ConfigError("generation.agent must be true or false")

    metadata = data.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ConfigError("metadata must be a mapping")

    java_service = data.get("java_service", {})
    if java_service is None:
        java_service = {}
    if not isinstance(java_service, dict):
        raise ConfigError("java_service must be a mapping")

    return EvalRunConfig(
        name=name,
        generation=GenerationConfig(agent=agent),
        java_service=java_service,
        metadata=metadata,
    )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by eval config files.

    Supports nested mappings via two-space indentation and scalar values
    (strings, booleans, integers, floats, null). This avoids adding a runtime
    dependency for the initial A/B config format.
    """

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent % 2 != 0:
            raise ConfigError(f"Invalid indentation on line {line_no}")

        stripped = line.strip()
        if ":" not in stripped:
            raise ConfigError(f"Expected key: value on line {line_no}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ConfigError(f"Empty key on line {line_no}")

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ConfigError(f"Invalid indentation on line {line_no}")

        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)

    return root


def _parse_scalar(value: str) -> Any:
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "none", "~"}:
        return None

    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value
