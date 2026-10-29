"""Exercise the real CLI in disposable repositories, including attempted baseline masking."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "baselines/eval_regression_gate.json"
CONFIG = "configs/eval_regression_gate.json"
SCRIPT = "scripts/eval_regression_gate.py"


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def commit(repo):
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Gate Test", "-c", "user.email=gate@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture revision")
    return git(repo, "rev-parse", "HEAD")


def cli(repo, *args):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=repo, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(ROOT / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "tests/fixtures/replay", tmp_path / "tests/fixtures/replay")
    git(tmp_path, "init", "-qb", "codex/gate-test")
    base = commit(tmp_path)
    for name in (SCRIPT, CONFIG):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    generated = cli(tmp_path, "baseline", "--source-ref", base)
    assert generated.returncode == 0, generated.stderr
    return tmp_path, base


def degrade_scorer(repo):
    path = repo / "src/llm_codegen_eval/evaluators/html_eval.py"
    text = path.read_text()
    assert "return min(100, score)" in text
    path.write_text(text.replace("return min(100, score)", "return min(100, max(0, score - 1))"))


def check(repo, base):
    return cli(repo, "check", "--base-ref", base, "--report", "gate-report.md")


def test_bootstrap_unchanged_passes_with_main_provenance(repo):
    root, base = repo
    result = check(root, base)
    assert result.returncode == 0, result.stdout + result.stderr
    baseline = json.loads((root / BASELINE).read_text())
    assert baseline["source_commit"] == base
    assert f"--source-ref {base}" in baseline["generation_command"]
    assert [r["score"] for r in baseline["results"]] == [17, 100]
    assert len({r["fixture_id"] for r in baseline["results"]}) == 2
    assert {r["case_id"] for r in baseline["results"]} == {"html_005"}
    assert "**PASS**" in (root / "gate-report.md").read_text()
    assert "Bootstrap" in result.stdout


def test_bootstrap_rejects_forged_baseline(repo):
    root, base = repo
    path = root / BASELINE
    data = json.loads(path.read_text())
    data["results"][0]["score"] = 0
    path.write_text(json.dumps(data))
    result = check(root, base)
    assert result.returncode == 1
    assert "bootstrap baseline does not equal" in result.stdout


def test_bootstrap_rejects_lower_scores(repo):
    root, base = repo
    degrade_scorer(root)
    result = check(root, base)
    assert result.returncode == 1
    assert "100 -> 99" in result.stdout
    assert "17 -> 16" in result.stdout


def test_established_baseline_unchanged_passes(repo):
    root, _ = repo
    base = commit(root)
    result = check(root, base)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Bootstrap" not in result.stdout
    assert "**PASS**" in result.stdout


def test_lower_pr_baseline_and_looser_thresholds_cannot_mask_drop(repo):
    root, _ = repo
    base = commit(root)
    degrade_scorer(root)
    path = root / BASELINE
    data = json.loads(path.read_text())
    for row in data["results"]:
        row["score"] = 0
    data["summary"] = {name: 0 for name in data["summary"]}
    path.write_text(json.dumps(data))
    path = root / CONFIG
    config = json.loads(path.read_text())
    config["max_drop"] = {name: 100 for name in config["max_drop"]}
    path.write_text(json.dumps(config))
    result = check(root, base)
    assert result.returncode == 1
    assert "100 -> 99; drop 1 exceeds 0" in result.stdout
    assert "17 -> 16; drop 1 exceeds 0" in result.stdout
    report = (root / "gate-report.md").read_text()
    assert "BASELINE / THRESHOLD / INPUT CHANGES" in report
    assert BASELINE in report and CONFIG in report
    assert "**FAIL**" in report


def test_pr_fixture_edits_cannot_hide_a_drop(repo):
    root, _ = repo
    base = commit(root)
    degrade_scorer(root)
    (root / "tests/fixtures/replay/html_005_bad.json").unlink()
    result = check(root, base)
    assert result.returncode == 1
    assert "html_005_bad.json#0 score: 17 -> 16" in result.stdout
    assert "INPUT CHANGES" in result.stdout


def test_false_positive_on_known_bad_fixture_fails(repo):
    root, _ = repo
    base = commit(root)
    path = root / "src/llm_codegen_eval/evaluators/html_eval.py"
    path.write_text(path.read_text().replace("passed=passed,", "passed=True,"))
    result = check(root, base)
    assert result.returncode == 1
    assert "expected False, got True" in result.stdout


def test_network_attempt_fails_and_still_writes_report(repo):
    root, _ = repo
    base = commit(root)
    path = root / "src/llm_codegen_eval/evaluators/html_eval.py"
    path.write_text("import socket\nsocket.create_connection(('example.invalid', 443))\n" + path.read_text())
    result = check(root, base)
    assert result.returncode == 1
    assert "Network access is forbidden" in result.stdout
    assert "**FAIL**" in (root / "gate-report.md").read_text()


def test_missing_baseline_fails_closed(repo):
    root, _ = repo
    base = commit(root)
    (root / BASELINE).unlink()
    result = check(root, base)
    assert result.returncode == 1
    assert BASELINE in result.stdout
    assert (root / "gate-report.md").exists()
