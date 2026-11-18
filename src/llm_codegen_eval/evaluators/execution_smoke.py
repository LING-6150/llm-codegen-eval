"""Smoke-level execution validation for generated artifacts."""

from __future__ import annotations

import mimetypes
import re
import time
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from ..core.case import CodeType, ElementCheck, EvalCase
from ..core.result import ExecutionSmokeResult
from .browser_artifact import project_files


FATAL_CONSOLE_TYPES = {"error"}
ARTIFACT_ORIGIN = "https://artifact.invalid"
ARTIFACT_POLICY = (
    "sandbox allow-scripts allow-same-origin; default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; worker-src 'none'; form-action 'none'; base-uri 'self'"
)


async def evaluate_execution_smoke(
    code: str,
    case: EvalCase,
    timeout_ms: int = 5000,
    playwright_factory: Any | None = None,
) -> ExecutionSmokeResult:
    """Run a thin browser smoke check for generated HTML-like artifacts.

    This is intentionally not full functional correctness. It checks that the
    artifact can load, avoids fatal console/page errors, and exposes required
    selectors when the structural case already defines them.
    """

    start = time.perf_counter()
    if case.code_type not in {CodeType.HTML, CodeType.MULTI_FILE}:
        return _result(
            applicable=False,
            passed=False,
            failure_type="not_applicable",
            detail=f"Execution smoke not implemented for code_type={case.code_type.value}",
            start=start,
        )

    html = extract_runnable_html(code)
    if case.code_type == CodeType.MULTI_FILE:
        try:
            entry, files = project_files(code, html)
        except ValueError as exc:
            return _result(True, False, "checker_error", str(exc), start)
    elif html:
        entry, files = "index.html", {"index.html": html}
    else:
        return _result(
            applicable=True,
            passed=False,
            failure_type="load_failure",
            detail="No runnable HTML document could be extracted",
            start=start,
        )

    selectors = _required_browser_selectors(case.required_checks)
    try:
        if playwright_factory is None:
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                return _result(
                    applicable=True,
                    passed=False,
                    failure_type="checker_error",
                    detail=(
                        "Playwright is not installed. Install it with "
                        "`uv add playwright` and `uv run playwright install chromium`."
                    ),
                    start=start,
                    checked_selectors=selectors,
                )
            playwright_factory = async_playwright

        return await _run_html_smoke(
            entry=entry,
            files=files,
            checks=case.required_checks,
            timeout_ms=timeout_ms,
            playwright_factory=playwright_factory,
            start=start,
        )
    except Exception as exc:
        return _result(
            applicable=True,
            passed=False,
            failure_type="checker_error",
            detail=str(exc),
            start=start,
            checked_selectors=selectors,
        )


def extract_runnable_html(code: str) -> str | None:
    """Extract the first runnable HTML document from LLM text."""

    fenced = re.search(r"```html\s*(.*?)```", code, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    html_start = _first_html_start(code)
    if html_start is not None:
        html = code[html_start:]
        fence_end = html.find("```")
        if fence_end != -1:
            html = html[:fence_end]
        return html.strip()

    if re.search(r"<(?:head|body|main|section|div|script|style|h1|form)\b", code, re.IGNORECASE):
        return code.strip()

    return None


async def _run_html_smoke(
    entry: str,
    files: dict[str, str],
    checks: list[ElementCheck],
    timeout_ms: int,
    playwright_factory: Any,
    start: float,
) -> ExecutionSmokeResult:
    console_errors: list[str] = []
    page_errors: list[str] = []
    selectors = _required_browser_selectors(checks)

    async def serve(route):
        url = urlsplit(route.request.url)
        path = unquote(url.path.removeprefix("/"))
        if (url.scheme, url.netloc) != ("https", "artifact.invalid") or path not in files:
            await route.abort("blockedbyclient")
            return
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        await route.fulfill(body=files[path].encode("utf-8"), headers={
            "Content-Type": f"{mime}; charset=utf-8",
            "Content-Security-Policy": ARTIFACT_POLICY,
            "X-DNS-Prefetch-Control": "off",
        })

    async with playwright_factory() as p:
        # Playwright controls Chromium over a pipe. All artifact responses come
        # from serve(); Chromium has no usable upstream proxy or DNS resolver.
        browser = await p.chromium.launch(args=[
            "--proxy-server=http://unreachable.invalid:1",
            "--proxy-bypass-list=<-loopback>",
            "--host-resolver-rules=MAP * ~NOTFOUND",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        ])
        try:
            context = await browser.new_context(offline=True, service_workers="block", accept_downloads=False)
            await context.route("**/*", serve)
            await context.route_web_socket("**/*", lambda socket: socket.close())
            page = await context.new_page()
            page.on("console", lambda msg: console_errors.append(msg.text)
                    if msg.type in FATAL_CONSOLE_TYPES else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            await page.goto(f"{ARTIFACT_ORIGIN}/{quote(entry)}", wait_until="load", timeout=timeout_ms)
            missing = await _missing_required_selectors(page, checks)
        finally:
            await browser.close()

    if page_errors:
        return _result(
            applicable=True,
            passed=False,
            failure_type="console_error",
            detail=f"Page error: {page_errors[0][:300]}",
            start=start,
            checked_selectors=selectors,
        )
    if console_errors:
        return _result(
            applicable=True,
            passed=False,
            failure_type="console_error",
            detail=f"Console error: {console_errors[0][:300]}",
            start=start,
            checked_selectors=selectors,
        )
    if missing:
        return _result(
            applicable=True,
            passed=False,
            failure_type="missing_element",
            detail="; ".join(missing[:5]),
            start=start,
            checked_selectors=selectors,
        )

    return _result(
        applicable=True,
        passed=True,
        failure_type="none",
        detail=None,
        start=start,
        checked_selectors=selectors,
    )


async def _missing_required_selectors(page: Any, checks: list[ElementCheck]) -> list[str]:
    missing = []
    for check in checks:
        if not check.selector:
            continue
        try:
            locator = page.locator(check.selector)
            count = await locator.count()
            if check.type == "tag_exists" and count < 1:
                missing.append(f"{check.description}: selector `{check.selector}` not found")
            elif check.type == "tag_count":
                expected = check.expected if isinstance(check.expected, int) else 1
                if count < expected:
                    missing.append(
                        f"{check.description}: selector `{check.selector}` count {count} < {expected}"
                    )
            elif check.type == "attr_exists":
                if count < 1:
                    missing.append(f"{check.description}: selector `{check.selector}` not found")
                    continue
                if not check.attribute:
                    continue
                has_attr = await locator.evaluate_all(
                    "(els, attr) => els.some(el => el.hasAttribute(attr))",
                    check.attribute,
                )
                if not has_attr:
                    missing.append(
                        f"{check.description}: selector `{check.selector}` missing attr `{check.attribute}`"
                    )
        except Exception as exc:
            missing.append(f"{check.description}: selector check failed ({exc})")
    return missing


def _required_browser_selectors(checks: list[ElementCheck]) -> list[str]:
    return [
        check.selector
        for check in checks
        if check.selector and check.type in {"tag_exists", "tag_count", "attr_exists"}
    ]


def _first_html_start(code: str) -> int | None:
    starts = [
        idx
        for idx in (
            _find_case_insensitive(code, "<!doctype"),
            _find_case_insensitive(code, "<html"),
        )
        if idx != -1
    ]
    return min(starts) if starts else None


def _find_case_insensitive(text: str, needle: str) -> int:
    return text.lower().find(needle.lower())


def _result(
    applicable: bool,
    passed: bool,
    failure_type: str,
    detail: str | None,
    start: float,
    checked_selectors: list[str] | None = None,
) -> ExecutionSmokeResult:
    return ExecutionSmokeResult(
        applicable=applicable,
        passed=passed,
        failure_type=failure_type,
        detail=detail,
        duration_ms=max(0, int((time.perf_counter() - start) * 1000)),
        checked_selectors=checked_selectors or [],
    )
