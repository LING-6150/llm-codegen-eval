import io
import zipfile

import pytest

from llm_codegen_eval.core.case import CodeType, Difficulty, ElementCheck, EvalCase
from llm_codegen_eval.core.final_artifact import (
    content_hash,
    extract_zip_files,
    serialize_for_evaluator,
)
from llm_codegen_eval.core.reporter import generate_markdown
from llm_codegen_eval.core.result import EvalResult, ExecutionSmokeResult
from llm_codegen_eval.core.runner import _build_repair_prompt, run_case
from llm_codegen_eval.evaluators.execution_smoke import evaluate_execution_smoke_files
from llm_codegen_eval.evaluators.vue_eval import VueEvaluator


def make_zip(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def timer_case(code_type: CodeType = CodeType.HTML) -> EvalCase:
    return EvalCase(
        case_id="timer_fake",
        prompt="A countdown timer app",
        code_type=code_type,
        difficulty=Difficulty.EASY,
        required_checks=[
            ElementCheck(type="tag_exists", selector="button", description="Start button"),
            ElementCheck(type="regex_match", pattern="setInterval", description="Uses a timer"),
        ],
    )


# Stream: CodeGen's first-shot HTML without a timer, then RefineAgent narration.
STREAM_CODE = (
    "```html\n<html><body><button>Start</button></body></html>\n```\n"
    "I read index.html and added the countdown logic with the Modify File tool."
)
# Disk: the file after RefineAgent's tool edit.
FINAL_HTML = "<html><body><button>Start</button><script>setInterval(() => {}, 1000)</script></body></html>"


class ArtifactClient:
    def __init__(self, before: bytes | None, after: bytes, generated_type="html", app_type="html"):
        self.downloads = [before, after]
        self.generated_type = generated_type
        self.app_type = app_type

    async def generate(self, prompt, agent=True, extra_params=None):
        # The run replaces the directory contents; later downloads see the new files.
        self.downloads.pop(0)
        return {
            "code": STREAM_CODE,
            "review_score": 80,
            "review_passed": True,
            "duration_ms": 1500,
            "error": None,
            "code_gen_type": self.generated_type,
        }

    async def get_app_code_gen_type(self):
        return self.app_type

    async def download_artifact(self):
        data = self.downloads[0]
        if data is None:
            raise RuntimeError("Project directory not found")
        return data


def test_extract_zip_files_skips_ignored_unsafe_and_binary_entries():
    data = make_zip({
        "index.html": "<html></html>",
        "src/App.vue": "<template></template>",
        "node_modules/vue/index.js": "x",
        "dist/index.html": "built",
        "../escape.txt": "x",
        "logo.png": b"\x89PNG\r\n\x1a\n\xff\xfe",
    })

    files = extract_zip_files(data)

    assert files == {"index.html": "<html></html>", "src/App.vue": "<template></template>"}


def test_extract_zip_files_rejects_non_zip_error_bodies():
    with pytest.raises(ValueError, match="did not return a ZIP"):
        extract_zip_files(b'{"code":40400,"message":"Project directory not found"}')


def test_serialize_multi_file_uses_stream_fence_shape():
    text = serialize_for_evaluator(
        {"index.html": "<h1>Hi</h1>", "style.css": "h1{}", "script.js": "go()"},
        CodeType.MULTI_FILE,
    )

    assert text == "```html\n<h1>Hi</h1>\n```\n\n```css\nh1{}\n```\n\n```javascript\ngo()\n```"


@pytest.mark.asyncio
async def test_serialized_vue_project_is_parsed_by_vue_evaluator():
    case = EvalCase(
        case_id="vue_fake",
        prompt="Vue counter",
        code_type=CodeType.VUE_PROJECT,
        difficulty=Difficulty.EASY,
        required_checks=[ElementCheck(type="regex_match", pattern="ref\\(", description="Reactive state")],
    )
    text = serialize_for_evaluator(
        {
            "package.json": '{"dependencies": {"vue": "^3.4.0"}}',
            "src/App.vue": "<template><p>{{ n }}</p></template>\n<script setup>const n = ref(0)</script>",
            "src/main.js": "import { createApp } from 'vue'",
        },
        CodeType.VUE_PROJECT,
    )

    result = await VueEvaluator().evaluate(text, case)

    assert result.passed
    assert result.error is None


@pytest.mark.asyncio
async def test_final_artifact_scores_refined_files_separately_from_stream():
    client = ArtifactClient(
        before=make_zip({"index.html": "<html>old run</html>"}),
        after=make_zip({"index.html": FINAL_HTML}),
    )

    result = await run_case(timer_case(), client, score_final_artifact=True)

    # Legacy stream score is unchanged: first-shot HTML has no timer.
    assert result.passed is False
    assert result.final_artifact is not None
    assert result.final_artifact.available
    assert result.final_artifact.passed
    assert result.final_artifact.files == ["index.html"]
    assert result.final_artifact.generated_code_gen_type == "html"


@pytest.mark.asyncio
async def test_final_artifact_is_unavailable_when_generated_type_differs_from_app_type():
    client = ArtifactClient(
        before=None,
        after=make_zip({"index.html": FINAL_HTML}),
        generated_type="multi_file",
        app_type="html",
    )

    result = await run_case(timer_case(), client, score_final_artifact=True)

    assert result.final_artifact is not None
    assert not result.final_artifact.available
    assert "differs from app type" in result.final_artifact.error


@pytest.mark.asyncio
async def test_final_artifact_is_unavailable_when_directory_did_not_change():
    same = make_zip({"index.html": FINAL_HTML})
    client = ArtifactClient(before=same, after=same)

    result = await run_case(timer_case(), client, score_final_artifact=True)

    assert result.final_artifact is not None
    assert not result.final_artifact.available
    assert "unchanged" in result.final_artifact.error


@pytest.mark.asyncio
async def test_final_artifact_download_failure_does_not_fail_the_run():
    client = ArtifactClient(before=None, after=b"not a zip")

    result = await run_case(timer_case(), client, score_final_artifact=True)

    assert result.error is None
    assert result.final_artifact is not None
    assert not result.final_artifact.available
    assert "Final artifact unavailable" in result.final_artifact.error


@pytest.mark.asyncio
async def test_final_artifact_files_are_saved_when_dir_given(tmp_path):
    client = ArtifactClient(before=None, after=make_zip({"index.html": FINAL_HTML}))

    result = await run_case(
        timer_case(),
        client,
        score_final_artifact=True,
        final_artifact_dir=tmp_path / "timer_run1",
    )

    assert (tmp_path / "timer_run1" / "index.html").read_text() == FINAL_HTML
    assert result.final_artifact.content_sha256 == content_hash({"index.html": FINAL_HTML})


def test_repair_prompt_does_not_leak_case_selectors():
    first_shot = EvalResult(
        case_id="timer_fake",
        passed=False,
        score=40,
        required_passed=1,
        required_total=2,
        optional_passed=0,
        optional_total=0,
        generated_code="<html></html>",
        execution_smoke=ExecutionSmokeResult(
            applicable=True,
            passed=False,
            failure_type="missing_element",
            detail="Start button: selector `button.start-btn` not found",
        ),
    )

    prompt = _build_repair_prompt(timer_case(), first_shot)

    assert "missing_element" in prompt
    assert "button.start-btn" not in prompt


def test_legacy_report_has_no_final_artifact_section():
    legacy = EvalResult(
        case_id="timer_fake",
        passed=True,
        score=100,
        required_passed=2,
        required_total=2,
        optional_passed=0,
        optional_total=0,
    )

    report = generate_markdown([legacy], [timer_case()])

    assert "Final Artifact" not in report
    assert "Final-artifact" not in report


@pytest.mark.asyncio
async def test_report_shows_stream_vs_final_agreement():
    client = ArtifactClient(before=None, after=make_zip({"index.html": FINAL_HTML}))
    result = await run_case(timer_case(), client, score_final_artifact=True)

    report = generate_markdown([result], [timer_case()])

    assert "## Final Artifact (post-Review/Refine files)" in report
    assert "final-only pass 1" in report
    assert "Final-artifact structural pass rate (post-Review/Refine files)**: 100.0% (1/1)" in report


@pytest.mark.asyncio
async def test_smoke_files_loads_sibling_script_in_real_browser():
    pytest.importorskip("playwright.async_api")
    files = {
        "index.html": '<html><body><button>Start</button><script src="script.js"></script></body></html>',
        "script.js": "document.body.appendChild(document.createElement('main')); missingFn();",
    }

    result = await evaluate_execution_smoke_files(files, timer_case(CodeType.MULTI_FILE))

    if result.failure_type == "checker_error":
        pytest.skip(f"Chromium unavailable: {result.detail}")
    # The sibling script ran, so its runtime error is caught.
    assert result.failure_type == "console_error"
    assert "missingFn" in (result.detail or "")
