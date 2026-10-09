"""Validate instruction/output pairs, reject benchmark leakage, and split by prompt."""
import argparse
import hashlib
import json
import random
import re
import unicodedata
from pathlib import Path
from ..serving.benchmark import CASES


def prompt_key(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).strip()).casefold()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(source: Path, benchmark: Path, output: Path, seed=42, validation_fraction=.2):
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between zero and one")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) < 5:
        raise ValueError("Need at least five examples for a train/validation smoke split")
    reserved = {prompt_key(c["prompt"]) for c in json.loads(benchmark.read_text(encoding="utf-8"))}
    seen = set()
    for row in rows:
        if set(row) != {"prompt", "completion"} or not all(isinstance(v, str) and v.strip() for v in row.values()):
            raise ValueError("Each row must have nonempty prompt and completion strings")
        key = prompt_key(row["prompt"])
        if key in reserved:
            raise ValueError("Training input overlaps a held-out benchmark prompt")
        if key in seen:
            raise ValueError("Duplicate prompt: deduplicate before splitting")
        seen.add(key)
    random.Random(seed).shuffle(rows)
    count = max(1, min(len(rows)-1, round(len(rows)*validation_fraction)))
    # New output directory prevents accidental overwrite of earlier experiment data.
    output.mkdir(parents=True, exist_ok=False)
    for name, split in (("validation", rows[:count]), ("train", rows[count:])):
        (output/f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in split), encoding="utf-8")
    manifest = {"schema_version": 1, "seed": seed, "source_sha256": digest(source),
                "benchmark_sha256": digest(benchmark), "train_rows": len(rows)-count, "validation_rows": count,
                "train_sha256": digest(output/"train.jsonl"), "validation_sha256": digest(output/"validation.jsonl"),
                "leakage_check": "normalized exact prompt match; semantic duplicates still require human review"}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

def verify(data: Path):
    manifest = json.loads((data/"manifest.json").read_text())
    for split in ("train", "validation"):
        if digest(data/f"{split}.jsonl") != manifest[f"{split}_sha256"]:
            raise ValueError("Dataset changed after preparation; prepare a new split")
    return manifest

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--benchmark", type=Path, default=CASES)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    print(json.dumps(prepare(args.source, args.benchmark, args.output, args.seed), indent=2))

if __name__ == "__main__":
    main()
