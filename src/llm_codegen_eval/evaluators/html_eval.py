"""HTML code evaluator."""

import re
from bs4 import BeautifulSoup
from .base import BaseEvaluator
from ..core.case import EvalCase, ElementCheck
from ..core.result import EvalResult

class HtmlEvaluator(BaseEvaluator):

    async def evaluate(self, code: str, case: EvalCase) -> EvalResult:
        try:
            soup = BeautifulSoup(code, 'html.parser')
        except Exception as e:
            return EvalResult(
                case_id=case.case_id,
                passed=False,
                score=0,
                required_passed=0,
                required_total=len(case.required_checks),
                optional_passed=0,
                optional_total=len(case.optional_checks),
                generated_code=code,
                error=f"HTML parse error: {e}"
            )

        required_passed = 0
        required_failed = []
        for check in case.required_checks:
            if self._run_check(soup, code, check):
                required_passed += 1
            else:
                required_failed.append(check)

        optional_passed = sum(
            1 for c in case.optional_checks
            if self._run_check(soup, code, c)
        )

        forbidden_found = [
            p for p in case.forbidden_patterns
            if re.search(p, code, re.IGNORECASE)
        ]

        required_total = len(case.required_checks)
        passed = (
            required_passed == required_total and
            len(forbidden_found) == 0
        )

        score = self._compute_score(
            required_passed, required_total,
            optional_passed, len(case.optional_checks),
            forbidden_found
        )

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
            generated_code=code
        )

    def _run_check(self, soup: BeautifulSoup, code: str, check: ElementCheck) -> bool:
        try:
            if check.type == "tag_exists":
                return bool(soup.select(check.selector))

            elif check.type == "tag_count":
                actual = len(soup.select(check.selector))
                expected = check.expected
                return actual >= expected if isinstance(expected, int) else False

            elif check.type == "attr_exists":
                elements = soup.select(check.selector)
                return any(el.has_attr(check.attribute) for el in elements)

            elif check.type == "text_contains":
                return str(check.expected).lower() in soup.get_text().lower()

            elif check.type == "regex_match":
                return bool(re.search(check.pattern, code))

            else:
                return False
        except Exception:
            return False

    def _compute_score(
        self,
        required_passed: int, required_total: int,
        optional_passed: int, optional_total: int,
        forbidden_found: list
    ) -> int:
        required_score = (required_passed / required_total * 70) if required_total else 70
        optional_score = (optional_passed / optional_total * 30) if optional_total else 30
        penalty = len(forbidden_found) * 20

        score = max(0, int(required_score + optional_score - penalty))
        return min(100, score)
