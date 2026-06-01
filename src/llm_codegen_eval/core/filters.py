"""Helpers for selecting benchmark cases from CLI filters."""

from .case import EvalCase


def parse_case_ids(raw_case_ids: str | None) -> list[str]:
    """Parse a comma-separated --case-id value into case ids."""
    if not raw_case_ids:
        return []
    return [case_id.strip() for case_id in raw_case_ids.split(",") if case_id.strip()]


def filter_cases_by_id(cases: list[EvalCase], case_ids: list[str]) -> list[EvalCase]:
    """Return cases matching case_ids, preserving requested order."""
    if not case_ids:
        return cases

    case_map = {case.case_id: case for case in cases}
    missing = [case_id for case_id in case_ids if case_id not in case_map]
    if missing:
        raise ValueError(f"Unknown case id(s): {', '.join(missing)}")

    return [case_map[case_id] for case_id in case_ids]
