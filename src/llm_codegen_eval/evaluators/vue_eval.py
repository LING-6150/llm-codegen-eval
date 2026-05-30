"""Vue project evaluator."""

import re
from dataclasses import dataclass

from .base import BaseEvaluator
from ..core.case import ElementCheck, EvalCase
from ..core.result import EvalResult


@dataclass(frozen=True)
class VueProjectFiles:
    package_json: str | None = None
    app_vue: str | None = None


class VueEvaluator(BaseEvaluator):
    """Evaluate generated Vue project text without requiring a filesystem."""

    async def evaluate(self, code: str, case: EvalCase) -> EvalResult:
        project_files = self._extract_project_files(code)
        required_passed = 0
        required_failed = []

        for check in case.required_checks:
            if self._run_check(code, check):
                required_passed += 1
            else:
                required_failed.append(check)

        optional_passed = sum(
            1 for check in case.optional_checks
            if self._run_check(code, check)
        )
        forbidden_found = [
            pattern for pattern in case.forbidden_patterns
            if re.search(pattern, code, re.IGNORECASE)
        ]
        structure_failed = self._structure_failures(project_files, code)

        required_total = len(case.required_checks)
        passed = (
            required_passed == required_total and
            not forbidden_found and
            not structure_failed
        )
        score = self._compute_score(
            required_passed,
            required_total,
            optional_passed,
            len(case.optional_checks),
            forbidden_found,
            structure_failed,
        )
        error = "; ".join(structure_failed) if structure_failed else None

        return EvalResult(
            case_id=case.case_id,
            passed=passed,
            score=score,
            required_passed=required_passed,
            required_total=required_total,
            required_failed=required_failed,
            optional_passed=optional_passed,
            optional_total=len(case.optional_checks),
            forbidden_found=forbidden_found,
            generated_code=code,
            error=error,
        )

    def _run_check(self, code: str, check: ElementCheck) -> bool:
        try:
            if check.type == "regex_match":
                if not check.pattern:
                    return False
                return bool(re.search(check.pattern, code, re.IGNORECASE | re.DOTALL))

            if check.type == "text_contains":
                return str(check.expected).lower() in code.lower()

            return False
        except Exception:
            return False

    def _extract_project_files(self, code: str) -> VueProjectFiles:
        package_json = self._extract_delimited_file(code, "package.json")
        app_vue = self._extract_delimited_file(code, "src/App.vue")

        if package_json is None and re.search(r"package\.json", code, re.IGNORECASE):
            package_json = code
        if app_vue is None and re.search(r"src/App\.vue|<template>|<script\s*setup", code, re.IGNORECASE):
            app_vue = code

        return VueProjectFiles(package_json=package_json, app_vue=app_vue)

    def _extract_delimited_file(self, code: str, file_path: str) -> str | None:
        escaped_path = re.escape(file_path)
        file_header = rf"(?:^|\n)\s*(?:#{1,6}\s*)?(?:file|path|filename)?\s*[:`]*\s*{escaped_path}\s*`?\s*\n"
        match = re.search(file_header, code, re.IGNORECASE)
        if not match:
            return None

        next_header = re.search(
            r"\n\s*(?:#{1,6}\s*)?(?:file|path|filename)?\s*[:`]*\s*"
            r"(?:[\w.-]+/)*[\w.-]+\.(?:vue|js|ts|json|css|html)\s*`?\s*\n",
            code[match.end():],
            re.IGNORECASE,
        )
        end = match.end() + next_header.start() if next_header else len(code)
        return code[match.end():end].strip()

    def _structure_failures(self, project_files: VueProjectFiles, code: str) -> list[str]:
        failures = []

        if not project_files.package_json:
            failures.append("Missing package.json")
        elif not re.search(r'["\']vue["\']\s*:', project_files.package_json, re.IGNORECASE):
            failures.append("package.json does not declare vue dependency")

        if not project_files.app_vue:
            failures.append("Missing src/App.vue")
        elif not re.search(r"<template[\s>]", project_files.app_vue, re.IGNORECASE):
            failures.append("src/App.vue does not include a template block")

        if not re.search(r"createApp\s*\(|from\s+[\"']vue[\"']|<script\s*setup|defineComponent", code):
            failures.append("Missing Vue entrypoint or component script")

        return failures

    def _compute_score(
        self,
        required_passed: int,
        required_total: int,
        optional_passed: int,
        optional_total: int,
        forbidden_found: list[str],
        structure_failed: list[str],
    ) -> int:
        required_score = (required_passed / required_total * 70) if required_total else 70
        optional_score = (optional_passed / optional_total * 30) if optional_total else 30
        penalty = len(forbidden_found) * 20 + len(structure_failed) * 15

        return min(100, max(0, int(required_score + optional_score - penalty)))
