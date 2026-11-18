"""Raw EvalResult serialization without live-run dependencies."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .case import EvalCase
from .result import EvalResult


TRUNCATION_MARKER = "... [truncated]"
GENERATED_CODE_TRUNCATE_CHARS = 2000


class RunWorkload(BaseModel):
    cases: list[EvalCase] = Field(min_length=1)
    runs_per_case: int = Field(gt=0)
    completed: bool

    @staticmethod
    def path_for(raw: Path) -> Path:
        return raw.with_name(f"workload_{raw.name}")

    @classmethod
    def load(cls, raw: Path) -> "RunWorkload | None":
        path = cls.path_for(raw)
        return cls.model_validate_json(path.read_bytes()) if path.is_file() else None

    def matches_rows(self, rows: list[EvalResult]) -> bool:
        return complete_case_runs(rows, self.cases, self.runs_per_case)


def complete_case_runs(rows: list[EvalResult], cases: list[EvalCase], repeats: int) -> bool:
    if not cases or repeats < 1 or len(rows) != len(cases) * repeats:
        return False
    expected_ids = {case.case_id for case in cases}
    if len(expected_ids) != len(cases):
        return False
    seen = set()
    for row in rows:
        index = row.run_config.get("run_index", 1 if repeats == 1 else None)
        if (row.case_id not in expected_ids or type(index) is not int or not 1 <= index <= repeats
                or row.run_config.get("runs_per_case", repeats) != repeats):
            return False
        seen.add((row.case_id, index))
    return len(seen) == len(rows)


def save_results(
    results: list[EvalResult],
    output_path: Path,
    *,
    workload: RunWorkload | None = None,
) -> None:
    """Save raw results as JSON for later analysis.

    The raw JSON keeps generated_code compact. When generated_code is truncated,
    a structured flag is written so replay code never has to infer truncation
    from the displayed text alone.
    """
    output_path.parent.mkdir(exist_ok=True, parents=True)

    serialized = []
    for result in results:
        d = result.model_dump(mode="json")
        generated_code = d.get("generated_code") or ""
        is_truncated = bool(d.get("generated_code_truncated", False))

        if generated_code and len(generated_code) > GENERATED_CODE_TRUNCATE_CHARS:
            d["generated_code"] = (
                generated_code[:GENERATED_CODE_TRUNCATE_CHARS] + TRUNCATION_MARKER
            )
            is_truncated = True

        d["generated_code_truncated"] = is_truncated
        serialized.append(d)

    output_path.write_text(
        json.dumps(serialized, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    if workload is not None:
        path = workload.path_for(output_path)
        staging = path.with_suffix(".tmp")
        staging.write_text(workload.model_dump_json(indent=2), encoding="utf-8")
        staging.replace(path)


def load_results(results_path: Path) -> list[EvalResult]:
    """Load raw EvalResult JSON from a previous benchmark run."""
    with open(results_path, encoding="utf-8") as f:
        data = json.load(f)

    return [EvalResult(**_with_legacy_truncation_flag(item)) for item in data]


def _with_legacy_truncation_flag(raw: dict) -> dict:
    """Mark legacy raws that used only the textual truncation marker."""
    if "generated_code_truncated" not in raw:
        generated_code = raw.get("generated_code") or ""
        raw = dict(raw)
        raw["generated_code_truncated"] = generated_code.endswith(TRUNCATION_MARKER)
    return raw
