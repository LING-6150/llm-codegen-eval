"""Explicit browser-only assertions; never inspect generated implementation code."""
from playwright.async_api import expect, Error as BrowserError
from .models import BehaviorCheck

CHECKS = {
    "timer": ["countdown-decreases", "pause-preserves-time", "resume-completes", "stays-at-zero", "reset-restores-input", "restart-new-duration"],
    "form": ["reject-empty-name", "reject-invalid-email", "submit-valid-values"],
    "todo": ["ignore-blank", "add-two-items", "toggle-only-one", "delete-only-selected"],
    "filter": ["initial-catalog", "case-insensitive-search", "combine-filters", "change-query", "clear-filters"],
    "notes": ["fresh-storage", "save-and-reload", "overwrite-and-reload", "clear-and-reload"],
}


class BehaviorFailure(Exception):
    pass


class Steps:
    def __init__(self, behavior_id):
        self.ids = CHECKS[behavior_id]
        self.results = []

    async def run(self, check_id, operation):
        from playwright.async_api import TimeoutError
        try:
            await operation()
        except (AssertionError, TimeoutError) as exc:
            self.results.append(BehaviorCheck(check_id=check_id, status="failed", detail=str(exc)[:2000]))
            raise BehaviorFailure() from exc
        except BrowserError as exc:
            # Invalid/ambiguous generated controls violate the public DOM contract.
            # Other browser/protocol errors remain checker errors in the outer runner.
            message = str(exc)
            if not any(pattern in message for pattern in (
                "Element is not an", "Element is not a", "Not an input element", "strict mode violation",
            )):
                raise
            self.results.append(BehaviorCheck(check_id=check_id, status="failed", detail=message[:2000]))
            raise BehaviorFailure() from exc
        else:
            self.results.append(BehaviorCheck(check_id=check_id, status="passed"))

    def complete(self):
        seen = {r.check_id for r in self.results}
        return self.results + [BehaviorCheck(check_id=i, status="not_run", detail="Earlier check did not complete") for i in self.ids if i not in seen]


async def text(page, test_id, expected):
    await expect(page.get_by_test_id(test_id)).to_have_text(expected, timeout=1000)


async def timer(page, s):
    async def decreases():
        await page.get_by_test_id("seconds").fill("3")
        await page.get_by_test_id("start").click()
        await text(page, "remaining", "3")
        await text(page, "status", "running")
        await page.clock.run_for(1000)
        await text(page, "remaining", "2")
    await s.run("countdown-decreases", decreases)
    async def pause():
        await page.get_by_test_id("pause").click()
        await page.clock.run_for(2000)
        await text(page, "remaining", "2")
        await text(page, "status", "paused")
    await s.run("pause-preserves-time", pause)
    async def resume():
        await page.get_by_test_id("start").click()
        await page.clock.run_for(2000)
        await text(page, "remaining", "0")
        await text(page, "status", "done")
    await s.run("resume-completes", resume)
    async def zero():
        await page.clock.run_for(2000)
        await text(page, "remaining", "0")
    await s.run("stays-at-zero", zero)
    async def reset():
        await page.get_by_test_id("reset").click()
        await text(page, "remaining", "3")
        await text(page, "status", "idle")
    await s.run("reset-restores-input", reset)
    async def restart():
        await page.get_by_test_id("seconds").fill("1")
        await page.get_by_test_id("start").click()
        await page.clock.run_for(1000)
        await text(page, "remaining", "0")
        await text(page, "status", "done")
    await s.run("restart-new-duration", restart)


async def form(page, s):
    async def empty():
        await page.get_by_test_id("submit").click()
        await text(page, "error", "Name required")
        await text(page, "status", "invalid")
        await text(page, "receipt", "")
    await s.run("reject-empty-name", empty)
    async def invalid():
        await page.get_by_test_id("name").fill("Ada")
        await page.get_by_test_id("email").fill("not-an-email")
        await page.get_by_test_id("submit").click()
        await text(page, "error", "Invalid email")
        await text(page, "status", "invalid")
    await s.run("reject-invalid-email", invalid)
    async def valid():
        await page.get_by_test_id("email").fill("ada@example.com")
        await page.get_by_test_id("submit").click()
        await text(page, "error", "")
        await text(page, "status", "submitted")
        await expect(page.get_by_test_id("receipt")).to_contain_text("Ada", timeout=1000)
        await expect(page.get_by_test_id("receipt")).to_contain_text("ada@example.com", timeout=1000)
    await s.run("submit-valid-values", valid)


async def todo(page, s):
    items = page.get_by_test_id("task")
    async def blank():
        await page.get_by_test_id("task-input").fill("   ")
        await page.get_by_test_id("add").click()
        await expect(items).to_have_count(0, timeout=1000)
    await s.run("ignore-blank", blank)
    async def add():
        for value in ["Write tests", "Ship report"]:
            await page.get_by_test_id("task-input").fill(value)
            await page.get_by_test_id("add").click()
        await expect(items).to_have_count(2, timeout=1000)
        await expect(items.nth(0).get_by_test_id("task-label")).to_have_text("Write tests", timeout=1000)
        await expect(items.nth(1).get_by_test_id("task-label")).to_have_text("Ship report", timeout=1000)
    await s.run("add-two-items", add)
    async def toggle():
        await items.nth(0).get_by_test_id("task-toggle").check()
        await expect(items.nth(0).get_by_test_id("task-toggle")).to_be_checked(timeout=1000)
        await expect(items.nth(1).get_by_test_id("task-toggle")).not_to_be_checked(timeout=1000)
    await s.run("toggle-only-one", toggle)
    async def delete():
        await items.nth(1).get_by_test_id("task-delete").click()
        await expect(items).to_have_count(1, timeout=1000)
        await expect(items.get_by_test_id("task-label")).to_have_text("Write tests", timeout=1000)
        await expect(items.get_by_test_id("task-toggle")).to_be_checked(timeout=1000)
    await s.run("delete-only-selected", delete)


async def filter(page, s):
    products = page.locator('[data-testid="product"]:visible')
    async def initial():
        await expect(products).to_have_count(4, timeout=1000)
    await s.run("initial-catalog", initial)
    async def search():
        await page.get_by_test_id("query").fill("oAk")
        await expect(products).to_have_count(1, timeout=1000)
        await expect(products).to_have_text("Oak Desk", timeout=1000)
    await s.run("case-insensitive-search", search)
    async def combined():
        await page.get_by_test_id("category").select_option("kitchen")
        await expect(products).to_have_count(0, timeout=1000)
    await s.run("combine-filters", combined)
    async def change():
        await page.get_by_test_id("query").fill("mug")
        await expect(products).to_have_count(1, timeout=1000)
        await expect(products).to_have_text("Blue Mug", timeout=1000)
    await s.run("change-query", change)
    async def clear():
        await page.get_by_test_id("query").fill("")
        await expect(products).to_have_count(2, timeout=1000)
        await page.get_by_test_id("category").select_option("all")
        await expect(products).to_have_count(4, timeout=1000)
    await s.run("clear-filters", clear)


async def notes(page, s):
    note = page.get_by_test_id("note")
    async def fresh():
        await expect(note).to_have_value("", timeout=1000)
    await s.run("fresh-storage", fresh)
    async def save():
        await note.fill("First line\nsecond line — persistent note")
        await page.get_by_test_id("save").click()
        await text(page, "status", "saved")
        await page.reload(wait_until="domcontentloaded")
        await expect(note).to_have_value("First line\nsecond line — persistent note", timeout=1000)
    await s.run("save-and-reload", save)
    async def overwrite():
        await note.fill("Replacement note")
        await page.get_by_test_id("save").click()
        await page.reload(wait_until="domcontentloaded")
        await expect(note).to_have_value("Replacement note", timeout=1000)
    await s.run("overwrite-and-reload", overwrite)
    async def clear():
        await page.get_by_test_id("clear").click()
        await expect(note).to_have_value("", timeout=1000)
        await text(page, "status", "cleared")
        await page.reload(wait_until="domcontentloaded")
        await expect(note).to_have_value("", timeout=1000)
    await s.run("clear-and-reload", clear)


SCENARIOS = {"timer": timer, "form": form, "todo": todo, "filter": filter, "notes": notes}
