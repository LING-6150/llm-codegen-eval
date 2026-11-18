import json
from pathlib import Path
from .models import BehaviorCase

SUITE_ROOT = Path(__file__).parents[1] / "benchmarks" / "behavior"
SUITE_NAME = "html-behavior-v1"


def load_behavior_cases() -> list[BehaviorCase]:
    data = json.loads((SUITE_ROOT / "cases.json").read_text(encoding="utf-8"))
    return [BehaviorCase.model_validate(case) for case in data]
