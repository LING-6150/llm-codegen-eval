"""Generation adapters for the public CLI; no Java/database setup required."""
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Protocol

from .clients.openai_client import OpenAIClient
from .core.case import EvalCase


@dataclass
class Generation:
    code: str
    duration_ms: float = 0
    metadata: dict = field(default_factory=dict)


class Generator(Protocol):
    async def generate(self, case: EvalCase) -> Generation: ...


class OpenAIGenerator:
    def __init__(self, client: OpenAIClient):
        self.client = client

    async def generate(self, case: EvalCase) -> Generation:
        response = await self.client.generate(case.prompt)
        return Generation(response["code"], response["duration_ms"], {
            "model": self.client.model, "usage": response.get("usage"),
            "ttft_ms": response.get("ttft_ms"), "finish_reason": response.get("finish_reason"),
        })


class ArtifactGenerator:
    """Re-evaluate complete saved HTML; never presented as fresh model generation."""
    def __init__(self, directory: Path):
        self.directory = directory.resolve(strict=True)
        if not self.directory.is_dir():
            raise ValueError("artifacts-dir must be a directory")

    async def generate(self, case: EvalCase) -> Generation:
        start = perf_counter()
        path = (self.directory / f"{case.case_id}.html").resolve(strict=True)
        if not path.is_relative_to(self.directory):
            raise ValueError("Artifact path escapes artifacts-dir")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("HTML artifact exceeds 2 MiB")
        code = path.read_text(encoding="utf-8")
        if not code.strip():
            raise ValueError("Empty HTML artifact")
        return Generation(code, (perf_counter() - start) * 1000, {"source": "saved-artifact"})
