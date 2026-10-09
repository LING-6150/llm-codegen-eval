"""Read-only, bounded access to serving and legacy raw results."""
import json
import re
from pathlib import Path
from ..core.result import EvalResult

class ResultStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _safe(self, path):
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Invalid report path")
        return resolved

    def ids(self):
        if not self.root.exists():
            return []
        paths = list(self.root.glob("raw_*.json")) + list((self.root / "serving").glob("*/results.json"))
        if len(paths) > 10000:
            raise ValueError("Too many report files; archive older reports")
        ids = []
        for path in paths:
            self._safe(path)
            run_id = path.stem if path.name != "results.json" else path.parent.name
            if re.fullmatch(r"[a-zA-Z0-9_-]{1,160}", run_id):
                ids.append(run_id)
        return sorted(set(ids), reverse=True)

    def _json(self, path):
        path = self._safe(path)
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Report exceeds 10 MiB read limit")
        return json.loads(path.read_text(encoding="utf-8"))

    def load(self, run_id):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,160}", run_id):
            raise ValueError("Invalid run ID")
        legacy = run_id.startswith("raw_")
        path = self.root / (f"{run_id}.json" if legacy else f"serving/{run_id}/results.json")
        path = self._safe(path)
        if not path.is_file():
            return None
        data = self._json(path)
        if not isinstance(data, list) or len(data) > 10000:
            raise ValueError("Invalid or oversized result collection")
        try:
            results = [EvalResult.model_validate(item) for item in data]
        except (ValueError, TypeError):
            raise ValueError("Invalid result report") from None
        metadata = {} if legacy else self._json(path.with_name("benchmark.json"))
        return metadata, results
