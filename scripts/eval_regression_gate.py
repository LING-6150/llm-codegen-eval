"""Compare deterministic artifact replay with the PR base's trusted baseline.

No generation, browser, Java service, or scorer changes. Imports of the selected
revision's replay code happen only in a fresh, network-disabled worker process.
"""

import argparse
import asyncio
import hashlib
import io
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile


CONFIG = "configs/eval_regression_gate.json"
BASELINE = "baselines/eval_regression_gate.json"
METRICS = (
    "mean_score_points",
    "structural_pass_rate_pp",
    "required_check_pass_rate_pp",
    "optional_check_pass_rate_pp",
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config):
    if config["schema_version"] != 1:
        raise ValueError("Unsupported gate config version")
    paths = [config["cases_path"], *config["fixtures"]]
    if not config["fixtures"] or len(set(paths)) != len(paths):
        raise ValueError("Fixture list must be nonempty and paths must be unique")
    for path in paths:
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError(f"Input path must be repository-relative: {path}")
    if set(config["max_drop"]) != {"fixture_score_points", *METRICS}:
        raise ValueError("All five regression thresholds must be explicit")
    for value in config["max_drop"].values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Thresholds must be finite nonnegative numbers")
    return config


def input_hashes(root, config):
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in [config["cases_path"], *config["fixtures"]]
    }


def summarize(rows):
    if not rows:
        raise ValueError("Cannot gate an empty fixture suite")
    return {
        "mean_score_points": sum(r["score"] for r in rows) / len(rows),
        "structural_pass_rate_pp": 100 * sum(r["passed"] for r in rows) / len(rows),
        "required_check_pass_rate_pp": 100 * sum(r["required_passed"] for r in rows) / sum(r["required_total"] for r in rows),
        "optional_check_pass_rate_pp": 100 * sum(r["optional_passed"] for r in rows) / sum(r["optional_total"] for r in rows),
    }


def worker(source, inputs, config):
    sys.path.insert(0, str(source / "src"))

    def no_network(*args, **kwargs):
        raise RuntimeError("Network access is forbidden in the offline eval gate")

    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    socket.getaddrinfo = no_network

    from llm_codegen_eval.core.cases_io import load_cases
    from llm_codegen_eval.core.replay import load_replay_artifacts, replay_artifacts

    async def evaluate():
        cases = load_cases(inputs / config["cases_path"])
        rows = []
        for name in config["fixtures"]:
            artifacts = load_replay_artifacts(inputs / name)
            if not artifacts:
                raise ValueError(f"Empty fixture: {name}")
            results = await replay_artifacts(artifacts, cases, execution_smoke=False)
            if len(results) != len(artifacts):
                raise ValueError(f"Missing results: {name}")
            for index, (artifact, result) in enumerate(zip(artifacts, results)):
                if not isinstance(artifact.expected_structural_passed, bool):
                    raise ValueError(f"Missing expected_structural_passed: {name}")
                if not 0 <= result.score <= 100:
                    raise ValueError(f"Invalid score: {name}: {result.score}")
                rows.append({
                    "fixture_id": f"{name}#{index}",
                    "case_id": result.case_id,
                    "expected_passed": artifact.expected_structural_passed,
                    **result.model_dump(include={
                        "passed", "score", "required_passed", "required_total",
                        "optional_passed", "optional_total", "error",
                    }),
                })
        return {"inputs": input_hashes(inputs, config), "results": rows, "summary": summarize(rows)}

    print(json.dumps(asyncio.run(evaluate()), allow_nan=False))


def score(source, inputs, config):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker",
         str(source), str(inputs), json.dumps(config)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise ValueError(f"Offline replay failed:\n{result.stderr}")
    return json.loads(result.stdout)


def snapshot(repo, ref, destination):
    sha = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=repo, text=True,
    ).strip()
    archive = subprocess.check_output(["git", "archive", sha], cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(archive)) as files:
        files.extractall(destination, filter="data")
    return sha


def baseline_payload(sha, evaluation):
    return {
        "schema_version": 1,
        "source_commit": sha,
        "generation_command": f"uv run python scripts/eval_regression_gate.py baseline --source-ref {sha}",
        **evaluation,
    }


def compare(baseline, current, config):
    failures, table = [], []
    previous = {r["fixture_id"]: r for r in baseline["results"]}
    actual = {r["fixture_id"]: r for r in current["results"]}
    if len(previous) != len(baseline["results"]) or len(actual) != len(current["results"]) or previous.keys() != actual.keys():
        raise ValueError("Fixture inventory changed or contains duplicate identifiers")
    if baseline["inputs"] != current["inputs"]:
        raise ValueError("Baseline input hashes do not match the fixed base fixtures/cases")

    def metric(label, before, after, limit):
        drop = before - after
        table.append(f"| {label} | {before:g} | {after:g} | {after - before:+g} | {limit:g} |")
        if drop > limit:
            failures.append(f"{label}: {before:g} -> {after:g}; drop {drop:g} exceeds {limit:g}")

    for key, row in actual.items():
        before = previous[key]
        metric(f"{key} score", before["score"], row["score"], config["max_drop"]["fixture_score_points"])
        if row["passed"] != before["expected_passed"]:
            failures.append(f"{key} passed: expected {before['expected_passed']}, got {row['passed']}")
        if row["error"]:
            failures.append(f"{key} evaluator error: {row['error']}")
        for field in ("required_passed", "optional_passed"):
            table.append(f"| {key} {field} | {before[field]} | {row[field]} | {row[field] - before[field]:+d} | — |")
    for name in METRICS:
        metric(name, baseline["summary"][name], current["summary"][name], config["max_drop"][name])
    return failures, table


def changed_controls(repo, base, config):
    paths = {BASELINE, CONFIG, config["cases_path"], *config["fixtures"]}
    paths.update(str(p.relative_to(repo)) for p in (repo / "tests/fixtures/replay").glob("*.json"))
    paths.update(str(p.relative_to(base)) for p in (base / "tests/fixtures/replay").glob("*.json"))
    return sorted(name for name in paths if
                  ((repo / name).read_bytes() if (repo / name).is_file() else None) !=
                  ((base / name).read_bytes() if (base / name).is_file() else None))


def check(repo, base_ref, report_path):
    lines = ["# Offline eval regression gate", ""]
    failures = []
    try:
        with tempfile.TemporaryDirectory(prefix="eval-gate-base-") as directory:
            base = Path(directory)
            sha = snapshot(repo, base_ref, base)
            bootstrap = not (base / BASELINE).exists()
            config = validate_config(read_json((repo if bootstrap else base) / CONFIG))
            proposed = read_json(repo / BASELINE)
            validate_config(read_json(repo / CONFIG))
            lines += [f"Base commit: `{sha}`", "",
                      "Scope: two HTML artifact fixtures; structural scoring only. No model/Java/browser calls.", ""]
            changed = changed_controls(repo, base, config)
            if changed:
                message = "BASELINE / THRESHOLD / INPUT CHANGES: " + ", ".join(changed)
                print(f"::warning::{message}")
                lines += [f"**{message}**", "",
                          "PR-side changes do not replace the base reference used for comparison.", ""]
            if bootstrap:
                lines += ["Bootstrap: base has no baseline. Recompute it using base code and base inputs; require exact equality with the proposed JSON. Thresholds come from the new, explicitly reviewed config.", ""]
                baseline = baseline_payload(sha, score(base, base, config))
                if proposed != baseline:
                    failures.append("Proposed bootstrap baseline does not equal the base commit's recomputed baseline")
            else:
                baseline = read_json(base / BASELINE)
                lines += ["Reference: baseline, thresholds and inputs from the base commit; scorer from the PR checkout.", ""]
            if baseline["schema_version"] != 1:
                raise ValueError("Unsupported baseline version")
            current = score(repo, base, config)
            regressions, table = compare(baseline, current, config)
            failures.extend(regressions)
            lines += ["| Fixture / metric | Baseline | Current | Delta | Allowed drop |",
                      "|---|---:|---:|---:|---:|", *table, ""]
    except Exception as exc:
        failures.append(str(exc))
    lines += ["**FAIL**" if failures else "**PASS**", ""]
    lines.extend(f"- {failure}" for failure in failures)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if failures else 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]), Path(sys.argv[3]), json.loads(sys.argv[4]))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("baseline", help="Explicitly generate a baseline from a committed main revision")
    generate.add_argument("--source-ref", required=True)
    gate = commands.add_parser("check", help="Check the current scorer against a PR base revision")
    gate.add_argument("--base-ref", required=True)
    gate.add_argument("--report", type=Path, default=Path("reports/eval-regression-gate.md"))
    args = parser.parse_args()
    repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    if args.command == "check":
        return check(repo, args.base_ref, args.report)
    config = validate_config(read_json(repo / CONFIG))
    with tempfile.TemporaryDirectory(prefix="eval-gate-source-") as directory:
        source = Path(directory)
        sha = snapshot(repo, args.source_ref, source)
        payload = baseline_payload(sha, score(source, source, config))
    destination = repo / BASELINE
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Baseline generated from {sha}: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
