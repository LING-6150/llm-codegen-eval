"""Load and interact with self-contained HTML on an isolated loopback origin."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from time import perf_counter
from urllib.parse import urlsplit

from ..core.result import ExecutionSmokeResult
from ..evaluators.execution_smoke import extract_runnable_html
from .checks import BehaviorFailure, SCENARIOS, Steps
from .models import BehaviorResult, BrowserOutcome


@contextmanager
def serve_html(html):
    content = html.encode("utf-8")
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/index.html":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            elif path == "/favicon.ico":
                self.send_response(204); self.end_headers()
            else:
                self.send_response(404); self.end_headers()
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html"
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=1)


def smoke_result(passed=False, failure_type="checker_error", detail=None):
    return ExecutionSmokeResult(applicable=True, passed=passed, failure_type=failure_type, detail=detail)


async def evaluate_browser(code, case, evidence_dir: Path | None = None, playwright_factory=None):
    start = perf_counter()
    outcome = BrowserOutcome(smoke_result(detail="Browser did not start"),
        BehaviorResult(status="not_run", detail="Browser smoke did not pass"))
    html = extract_runnable_html(code)
    if not html:
        outcome.smoke = smoke_result(failure_type="load_failure", detail="No runnable HTML")
        return outcome
    behavior_id = getattr(case, "behavior_id", None)
    if behavior_id not in SCENARIOS:
        outcome.smoke = ExecutionSmokeResult(applicable=False, passed=False, failure_type="not_applicable")
        outcome.behavior = BehaviorResult(status="not_applicable", detail="No behavior contract registered")
        return outcome
    browser = context = page = None
    steps = Steps(behavior_id)
    behavior_start = None
    trace_started = False
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout
        factory = playwright_factory or async_playwright
        with serve_html(html) as url:
            async with factory() as playwright:
                try:
                    browser = await playwright.chromium.launch()
                    context = await browser.new_context(service_workers="block", accept_downloads=False)
                    origin = urlsplit(url).netloc
                    async def route(request_route):
                        parsed = urlsplit(request_route.request.url)
                        if parsed.scheme == "http" and parsed.netloc == origin:
                            await request_route.continue_()
                        else:
                            outcome.blocked_requests.append(parsed.scheme + "://" + parsed.netloc)
                            await request_route.abort()
                    await context.route("**/*", route)
                    await context.route_web_socket("**/*", lambda websocket: websocket.close())
                    if evidence_dir is not None:
                        await context.tracing.start(screenshots=True, snapshots=True, sources=False)
                        trace_started = True
                    page = await context.new_page()
                    page.set_default_timeout(1000)
                    page.set_default_navigation_timeout(5000)
                    page.on("console", lambda message: outcome.console_errors.append(message.text[:2000]) if message.type == "error" else None)
                    page.on("pageerror", lambda error: outcome.page_errors.append(str(error)[:2000]))
                    if behavior_id == "timer":
                        fixed = datetime(2024, 1, 1, tzinfo=timezone.utc)
                        await page.clock.install(time=fixed)
                        await page.clock.pause_at(fixed + timedelta(seconds=1))
                    try:
                        await page.goto(url, wait_until="load")
                    except BrowserTimeout:
                        outcome.smoke = smoke_result(failure_type="load_failure", detail="Page load timed out")
                    else:
                        if outcome.page_errors or outcome.console_errors:
                            outcome.smoke = smoke_result(failure_type="console_error", detail=(outcome.page_errors + outcome.console_errors)[0])
                        else:
                            outcome.smoke = smoke_result(True, "none")
                            outcome.smoke.duration_ms = round((perf_counter() - start) * 1000)
                            behavior_start = perf_counter()
                            try:
                                await asyncio.wait_for(SCENARIOS[behavior_id](page, steps), timeout=20)
                            except BehaviorFailure:
                                outcome.behavior = BehaviorResult(status="failed", checks=steps.complete(), detail="Behavior assertion failed")
                            except asyncio.TimeoutError:
                                outcome.behavior = BehaviorResult(status="checker_error", checks=steps.complete(), detail="Behavior scenario deadline exceeded")
                            else:
                                runtime_errors = outcome.page_errors + outcome.console_errors
                                completed = steps.complete()
                                complete = all(check.status == "passed" for check in completed)
                                status = "failed" if runtime_errors else ("passed" if complete else "checker_error")
                                outcome.behavior = BehaviorResult(status=status, checks=completed,
                                    detail=runtime_errors[0] if runtime_errors else (None if complete else "Checker returned before all declared checks ran"))
                except Exception as exc:
                    if outcome.smoke.passed:
                        outcome.behavior = BehaviorResult(status="checker_error", checks=steps.complete(), detail=f"Browser/checker error: {type(exc).__name__}")
                    else:
                        outcome.smoke = smoke_result(detail=f"Browser/checker error: {type(exc).__name__}")
                finally:
                    if behavior_start is not None:
                        outcome.behavior.duration_ms = round((perf_counter() - behavior_start) * 1000)
                    if evidence_dir is not None:
                        if page is not None and not page.is_closed():
                            try:
                                await page.screenshot(path=str(evidence_dir / "final.png"), timeout=3000)
                                outcome.evidence["screenshot"] = "final.png"
                            except Exception as exc:
                                outcome.evidence_errors.append(f"Screenshot: {type(exc).__name__}")
                        if trace_started:
                            try:
                                await context.tracing.stop(path=str(evidence_dir / "trace.zip"))
                                outcome.evidence["trace"] = "trace.zip"
                            except Exception as exc:
                                outcome.evidence_errors.append(f"Trace: {type(exc).__name__}")
                    if browser is not None:
                        await browser.close()
    except Exception as exc:
        outcome.smoke = smoke_result(detail=f"Browser environment error: {type(exc).__name__}")
    if not outcome.smoke.duration_ms:
        outcome.smoke.duration_ms = round((perf_counter() - start) * 1000)
    if evidence_dir is not None:
        (evidence_dir / "browser.json").write_text(json.dumps({
            "console_errors": outcome.console_errors, "page_errors": outcome.page_errors,
            "blocked_requests": outcome.blocked_requests, "evidence_errors": outcome.evidence_errors,
        }, indent=2), encoding="utf-8")
        outcome.evidence["browser_log"] = "browser.json"
    return outcome
