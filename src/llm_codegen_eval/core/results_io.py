"""Raw EvalResult serialization without live-run dependencies."""

import json
from pathlib import Path

from .result import EvalResult


TRUNCATION_MARKER = "... [truncated]"
GENERATED_CODE_TRUNCATE_CHARS = 2000


def save_results(
    results: list[EvalResult],
    output_path: Path,
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
