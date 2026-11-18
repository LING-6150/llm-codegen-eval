import pytest

from llm_codegen_eval.core.case import CodeType, EvalCase, ElementCheck
from llm_codegen_eval.evaluators.execution_smoke import (
    evaluate_execution_smoke,
    extract_runnable_html,
)


class FakeConsoleMessage:
    def __init__(self, text: str, message_type: str = "error"):
        self.text = text
        self.type = message_type


class FakeLocator:
    def __init__(self, count: int, has_attr: bool = True):
        self._count = count
        self._has_attr = has_attr

    async def count(self):
        return self._count

    async def evaluate_all(self, script, arg):
        return self._has_attr


class FakePage:
    def __init__(self, selectors=None, console_error: str | None = None):
        self.handlers = {}
        self.selectors = selectors or {}
        self.console_error = console_error

    def on(self, event, handler):
        self.handlers[event] = handler

    async def goto(self, url, wait_until=None, timeout=None):
        if self.console_error and "console" in self.handlers:
            self.handlers["console"](FakeConsoleMessage(self.console_error))

    def locator(self, selector):
        value = self.selectors.get(selector, 0)
        if isinstance(value, tuple):
            return FakeLocator(value[0], has_attr=value[1])
        return FakeLocator(value)


class FakeBrowser:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page

    async def close(self):
        return None


class FakeChromium:
    def __init__(self, page, launch_error: Exception | None = None):
        self.page = page
        self.launch_error = launch_error

    async def launch(self):
        if self.launch_error:
            raise self.launch_error
        return FakeBrowser(self.page)


class FakePlaywrightContext:
    def __init__(self, page, launch_error: Exception | None = None):
        self.chromium = FakeChromium(page, launch_error=launch_error)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def fake_playwright(page):
    return lambda: FakePlaywrightContext(page)


def fake_playwright_launch_error(error: Exception):
    return lambda: FakePlaywrightContext(FakePage(), launch_error=error)


def html_case() -> EvalCase:
    return EvalCase(
        case_id="html_case",
        prompt="Create page",
        code_type=CodeType.HTML,
        required_checks=[
            ElementCheck(type="tag_exists", selector="h1", description="Heading"),
            ElementCheck(type="tag_count", selector=".card", expected=2, description="Cards"),
            ElementCheck(
                type="attr_exists",
                selector="form",
                attribute="id",
                description="Form id",
            ),
        ],
    )


def test_extract_runnable_html_prefers_html_fence():
    code = "Here you go:\n```html\n<html><body><h1>Hello</h1></body></html>\n```"

    assert extract_runnable_html(code) == "<html><body><h1>Hello</h1></body></html>"


def test_extract_runnable_html_finds_document_without_fence():
    code = "Explanation first\n<!DOCTYPE html><html><body>Ok</body></html>\nTrailing"

    assert extract_runnable_html(code).startswith("<!DOCTYPE html>")


@pytest.mark.asyncio
async def test_execution_smoke_passes_with_required_selectors():
    page = FakePage(selectors={"h1": 1, ".card": 3, "form": (1, True)})

    result = await evaluate_execution_smoke(
        "<html><body><h1>Hello</h1><form id='x'></form></body></html>",
        html_case(),
        playwright_factory=fake_playwright(page),
    )

    assert result.applicable is True
    assert result.passed is True
    assert result.failure_type == "none"
    assert result.checked_selectors == ["h1", ".card", "form"]


@pytest.mark.asyncio
async def test_execution_smoke_reports_console_error():
    page = FakePage(selectors={"h1": 1, ".card": 2, "form": (1, True)}, console_error="boom")

    result = await evaluate_execution_smoke(
        "<html><body><script>console.error('boom')</script></body></html>",
        html_case(),
        playwright_factory=fake_playwright(page),
    )

    assert result.passed is False
    assert result.failure_type == "console_error"
    assert "boom" in result.detail


@pytest.mark.asyncio
async def test_execution_smoke_reports_missing_element():
    page = FakePage(selectors={"h1": 1, ".card": 1, "form": (1, False)})

    result = await evaluate_execution_smoke(
        "<html><body><h1>Hello</h1></body></html>",
        html_case(),
        playwright_factory=fake_playwright(page),
    )

    assert result.passed is False
    assert result.failure_type == "missing_element"
    assert "Cards" in result.detail
    assert "Form id" in result.detail


@pytest.mark.asyncio
async def test_execution_smoke_reports_browser_launch_failure_as_checker_error():
    result = await evaluate_execution_smoke(
        "<html><body><h1>Hello</h1></body></html>",
        html_case(),
        playwright_factory=fake_playwright_launch_error(RuntimeError("browser missing")),
    )

    assert result.applicable is True
    assert result.passed is False
    assert result.failure_type == "checker_error"
    assert "browser missing" in result.detail
    assert result.checked_selectors == ["h1", ".card", "form"]


@pytest.mark.asyncio
async def test_execution_smoke_marks_vue_not_applicable_for_now():
    case = EvalCase(
        case_id="vue_case",
        prompt="Build Vue",
        code_type=CodeType.VUE_PROJECT,
    )

    result = await evaluate_execution_smoke("<template><h1>Hi</h1></template>", case)

    assert result.applicable is False
    assert result.passed is False
    assert result.failure_type == "not_applicable"


async def _real_browser_smoke_or_skip(code: str, case: EvalCase):
    result = await evaluate_execution_smoke(code, case)
    if result.failure_type == "checker_error" and result.detail and (
        "Executable doesn't exist" in result.detail
        or "playwright install" in result.detail
        or "BrowserType.launch" in result.detail
    ):
        pytest.skip(f"Playwright browser is not installed: {result.detail.splitlines()[0]}")
    return result


@pytest.mark.asyncio
async def test_real_browser_fixture_passes_known_good_html():
    result = await _real_browser_smoke_or_skip(
        """
        ```html
        <!doctype html>
        <html>
          <body>
            <h1>Ready</h1>
            <div class="card"></div>
            <div class="card"></div>
            <form id="contact"></form>
          </body>
        </html>
        ```
        """,
        html_case(),
    )

    assert result.applicable is True
    assert result.passed is True
    assert result.failure_type == "none"


@pytest.mark.asyncio
async def test_real_browser_fixture_reports_console_error():
    result = await _real_browser_smoke_or_skip(
        """
        <!doctype html>
        <html>
          <body>
            <h1>Ready</h1>
            <div class="card"></div>
            <div class="card"></div>
            <form id="contact"></form>
            <script>console.error("fixture boom")</script>
          </body>
        </html>
        """,
        html_case(),
    )

    assert result.passed is False
    assert result.failure_type == "console_error"
    assert "fixture boom" in result.detail


@pytest.mark.asyncio
async def test_real_browser_fixture_reports_missing_element():
    result = await _real_browser_smoke_or_skip(
        """
        <!doctype html>
        <html><body><h1>Ready</h1><div class="card"></div></body></html>
        """,
        html_case(),
    )

    assert result.passed is False
    assert result.failure_type == "missing_element"
    assert "Cards" in result.detail
    assert "Form id" in result.detail
