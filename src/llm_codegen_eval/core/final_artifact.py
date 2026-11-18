"""Score the files the Java service left on disk after Review/Refine.

The legacy pipeline scores the SSE stream text: CodeGen tokens plus the
RefineAgent's streamed narration. RefineAgent edits files through tools, so
those edits never appear in the stream. This module downloads the final
project ZIP and evaluates it separately, leaving the legacy fields untouched.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path, PurePosixPath

from .case import CodeType, EvalCase
from .result import FinalArtifactResult

# Mirrors ProjectDownloadServiceImpl.IGNORED_NAMES on the Java side.
IGNORED_PARTS = {"node_modules", ".git", "dist", "build", ".DS_Store", ".env", "target", ".mvn", ".idea", ".vscode"}
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 5_000_000

MULTI_FILE_FENCES = (
    ("index.html", "html"),
    ("style.css", "css"),
    ("script.js", "javascript"),
)


def extract_zip_files(data: bytes) -> dict[str, str]:
    """Return {relative_path: text} for the text files in a project ZIP.

    Skips ignored directories, unsafe paths, and files that are not UTF-8 text.
    """
    if not data.startswith(b"PK"):
        preview = data[:200].decode("utf-8", errors="replace")
        raise ValueError(f"Download did not return a ZIP archive: {preview}")

    files: dict[str, str] = {}
    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            path = _safe_relative_path(info.filename)
            if path is None or info.file_size > MAX_FILE_BYTES:
                continue
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError(f"Project ZIP exceeds {MAX_TOTAL_BYTES} bytes of files")
            try:
                files[path] = archive.read(info).decode("utf-8")
            except UnicodeDecodeError:
                continue
    return files


def serialize_for_evaluator(files: dict[str, str], code_type: CodeType) -> str:
    """Render files in the text shape the existing evaluators already parse."""
    if code_type == CodeType.HTML:
        return files.get("index.html", "")

    if code_type == CodeType.MULTI_FILE:
        known = {name for name, _ in MULTI_FILE_FENCES}
        blocks = [
            f"```{lang}\n{files[name]}\n```"
            for name, lang in MULTI_FILE_FENCES
            if name in files
        ]
        blocks.extend(
            f"### {path}\n{content}"
            for path, content in sorted(files.items())
            if path not in known
        )
        return "\n\n".join(blocks)

    return "\n\n".join(f"### {path}\n{content}" for path, content in sorted(files.items()))


async def evaluate_final_artifact(
    files: dict[str, str],
    case: EvalCase,
    execution_smoke: bool = False,
    artifact_dir: Path | None = None,
) -> FinalArtifactResult:
    """Run the same structural evaluator (and optional smoke) on the final files."""
    from .runner import _evaluate_generated_code
    from ..evaluators.execution_smoke import evaluate_execution_smoke_files

    if not files:
        return FinalArtifactResult(available=False, error="Project ZIP contained no text files")

    if artifact_dir is not None:
        write_files(files, artifact_dir)

    structural = await _evaluate_generated_code(serialize_for_evaluator(files, case.code_type), case)
    result = FinalArtifactResult(
        available=True,
        files=sorted(files),
        content_sha256=content_hash(files),
        artifact_path=str(artifact_dir) if artifact_dir is not None else None,
        passed=structural.passed,
        score=structural.score,
        required_passed=structural.required_passed,
        required_total=structural.required_total,
        required_failed=structural.required_failed,
        forbidden_found=structural.forbidden_found,
        error=structural.error,
    )
    if execution_smoke:
        result.execution_smoke = await evaluate_execution_smoke_files(files, case)
    return result


def write_files(files: dict[str, str], target_dir: Path) -> None:
    for path, content in files.items():
        destination = target_dir / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


def _safe_relative_path(name: str) -> str | None:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    if any(part in IGNORED_PARTS for part in path.parts):
        return None
    return path.as_posix()


def content_hash(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8") + b"\0" + files[path].encode("utf-8") + b"\0")
    return digest.hexdigest()
