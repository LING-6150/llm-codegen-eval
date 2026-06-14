"""Benchmark case loading without live-run dependencies."""

import json
from pathlib import Path

from .case import EvalCase


def load_cases(cases_path: Path) -> list[EvalCase]:
    """Load EvalCases from a JSON file."""
    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)
    return [EvalCase(**case) for case in data]
