from pathlib import Path

import pytest

from llm_codegen_eval.core.config import ConfigError, load_run_config


def test_load_run_config_reads_generation_agent(tmp_path: Path):
    config_path = tmp_path / "agent_off.yaml"
    config_path.write_text(
        "\n".join([
            "name: agent_off",
            "generation:",
            "  agent: false",
            "metadata:",
            "  hypothesis: Single-agent baseline",
        ]),
        encoding="utf-8",
    )

    config = load_run_config(config_path)

    assert config.name == "agent_off"
    assert config.generation.agent is False
    assert config.metadata["hypothesis"] == "Single-agent baseline"


def test_load_run_config_rejects_non_boolean_agent(tmp_path: Path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        "\n".join([
            "name: bad",
            "generation:",
            "  agent: maybe",
        ]),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="generation.agent"):
        load_run_config(config_path)
