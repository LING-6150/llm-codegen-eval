"""Public evaluation commands with API and offline artifact targets."""
import asyncio
import hashlib
import importlib.metadata
import platform
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import click
import httpx

from .clients.openai_client import OpenAIClient
from .core.case import CodeType, EvalCase
from .core.cases_io import load_cases
from .core.result import EvalResult
from .core.results_io import save_results
from .core.reporter import generate_markdown
from .core.layered_report import build_layer_report, markdown_layer_report, requested_checks_failed
from .core.result import BehaviorResult
from .behavior.suite import SUITE_NAME, SUITE_ROOT, load_behavior_cases
from .behavior.browser import evaluate_browser
from .evaluators.html_eval import HtmlEvaluator
from .evaluators.execution_smoke import evaluate_execution_smoke
from .generators import ArtifactGenerator, OpenAIGenerator

CASES = Path(__file__).parent / "benchmarks" / "cases.json"


def suite_cases(suite: str) -> list[EvalCase]:
    if suite == SUITE_NAME:
        return load_behavior_cases()
    if suite != "html":
        raise ValueError(f"Unknown suite: {suite}")
    return [c for c in load_cases(CASES) if c.code_type == CodeType.HTML]


def select_cases(suite, case_ids, limit):
    cases = suite_cases(suite)
    unknown = set(case_ids) - {c.case_id for c in cases}
    if unknown:
        raise click.UsageError("Unknown case IDs: " + ", ".join(sorted(unknown)))
    if case_ids:
        cases = [c for c in cases if c.case_id in case_ids]
    if limit is not None:
        cases = cases[:limit]
    ids = [c.case_id for c in cases]
    if not ids or len(set(ids)) != len(ids) or not all(re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids):
        raise click.UsageError("Suite needs unique, path-safe case IDs")
    return cases


async def evaluate_cases(generator, cases, repeats, destination, timeout, smoke, config, behavior=True):
    results = []
    artifacts = destination / "artifacts"
    artifacts.mkdir()
    for repeat in range(1, repeats + 1):
        for case in cases:
            try:
                generated = await asyncio.wait_for(generator.generate(case), timeout=timeout)
                if not generated.code.strip():
                    raise ValueError("Empty generated artifact")
            except Exception as exc:
                # Transport exception text can contain tokens/URLs or provider response bodies.
                result = EvalResult(case_id=case.case_id, passed=False, score=0,
                    required_passed=0, required_total=len(case.required_checks),
                    optional_passed=0, optional_total=len(case.optional_checks),
                    error=f"Generation failed: {type(exc).__name__}")
            else:
                artifact = Path("artifacts") / f"{case.case_id}-r{repeat:03d}.html"
                (destination / artifact).write_text(generated.code, encoding="utf-8")
                result = await HtmlEvaluator().evaluate(generated.code, case)
                result.generated_artifact_path = str(artifact)
                result.generation_duration_ms = round(generated.duration_ms)
                result.run_config["artifact_sha256"] = hashlib.sha256(generated.code.encode()).hexdigest()
                if behavior and getattr(case, "behavior_id", None):
                    evidence = Path("evidence") / f"{case.case_id}-r{repeat:03d}"
                    browser = await evaluate_browser(generated.code, case, destination / evidence)
                    result.execution_smoke = browser.smoke
                    result.behavior_result = browser.behavior
                    result.browser_evidence = {key: str(evidence / path) for key, path in browser.evidence.items()}
                    result.browser_diagnostics = {"console_errors": browser.console_errors, "page_errors": browser.page_errors,
                        "blocked_requests": browser.blocked_requests, "evidence_errors": browser.evidence_errors}
                else:
                    result.behavior_result = BehaviorResult(status="not_run" if getattr(case, "behavior_id", None) else "not_applicable",
                        detail="Behavior checks disabled" if getattr(case, "behavior_id", None) else "Suite has no behavior contract")
                    if smoke:
                        result.execution_smoke = await evaluate_execution_smoke(generated.code, case)
                result.run_config["generation"] = generated.metadata
                usage = generated.metadata.get("usage") or {}
                result.total_tokens = usage.get("total_tokens") or 0
            result.run_config.update({**config, "run_index": repeat})
            results.append(result)
    return results


@click.group()
def main():
    """Evaluate HTML from an OpenAI-compatible model or complete saved artifacts."""


@main.command("list-cases")
@click.option("--suite", type=click.Choice(["html", SUITE_NAME]), default="html", show_default=True)
def list_cases(suite):
    """Show case IDs and generation prompts without calling a provider."""
    for case in suite_cases(suite):
        click.echo(f"{case.case_id}  {case.prompt}")


@main.command()
@click.option("--target", required=True, help="openai:<model-id> or artifacts")
@click.option("--suite", type=click.Choice(["html", SUITE_NAME]), default="html", show_default=True)
@click.option("--case-id", "case_ids", multiple=True, help="Repeat to select specific case IDs")
@click.option("--limit", type=click.IntRange(min=1))
@click.option("--repeats", type=click.IntRange(min=1), default=1, show_default=True)
@click.option("--base-url", default="https://api.openai.com/v1", show_default=True)
@click.option("--artifacts-dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--max-tokens", type=click.IntRange(min=1), default=4096, show_default=True)
@click.option("--temperature", type=click.FloatRange(min=0, max=2), default=0.0)
@click.option("--seed", type=int, default=42)
@click.option("--timeout", type=click.FloatRange(min=1), default=180.0, help="Total generation timeout per attempt")
@click.option("--smoke/--no-smoke", default=False, help="Also run the existing browser smoke layer")
@click.option("--behavior/--no-behavior", default=True, help="Run all layers for behavior suites; disable explicitly for structural-only diagnostics")
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), default=Path("reports/runs"))
def run(target, suite, case_ids, limit, repeats, base_url, artifacts_dir, max_tokens,
        temperature, seed, timeout, smoke, behavior, output_dir):
    """Generate or import HTML, evaluate it, and save reports plus complete artifacts.

    Exit 0: all selected checks pass. Exit 1: evaluation/generation failures.
    Exit 2: invalid configuration. Artifact mode makes no provider calls.
    """
    cases = select_cases(suite, case_ids, limit)
    model = None
    if target.startswith("openai:") and target[7:].strip():
        model = target[7:]
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise click.UsageError("base-url must be an HTTP(S) URL without credentials, query or fragment")
        if artifacts_dir is not None:
            raise click.UsageError("artifacts-dir is only valid with target artifacts")
    elif target == "artifacts" and artifacts_dir is not None:
        pass
    else:
        raise click.UsageError("Use --target openai:<model-id> or --target artifacts --artifacts-dir <directory>")
    key = os.getenv("INFERENCE_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    if model and base_url.rstrip("/") == "https://api.openai.com/v1" and not key:
        raise click.UsageError("Set INFERENCE_API_KEY or OPENAI_API_KEY for the default endpoint")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    pending = output_dir / f".pending-{run_id}"
    config = {"target": target, "suite": suite, "source_kind": "live-generation" if model else "artifact-replay",
              "repeats": repeats, "smoke_enabled": smoke or (behavior and suite == SUITE_NAME),
              "behavior_enabled": behavior and suite == SUITE_NAME}
    if model:
        config["base_url"] = base_url.rstrip("/")
    workload = {"cases": [c.model_dump(mode="json") for c in cases], "repeats": repeats,
                "max_tokens": max_tokens, "temperature": temperature, "seed": seed}
    async def execute():
        if model:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10)) as http:
                generator = OpenAIGenerator(OpenAIClient(http, base_url, model, key, max_tokens, temperature, seed))
                return await evaluate_cases(generator, cases, repeats, pending, timeout, smoke, config, behavior)
        return await evaluate_cases(ArtifactGenerator(artifacts_dir), cases, repeats, pending, timeout, smoke, config, behavior)
    pending.mkdir(parents=True)
    try:
        results = asyncio.run(execute())
        save_results(results, pending / "results.json")
        (pending / "structural-report.md").write_text(generate_markdown(results, cases, config_name=target,
            config_details=config, top_banner="Saved-artifact replay; not a live model benchmark." if not model else None), encoding="utf-8")
        metadata = {"schema_version": 1, "run_id": run_id, **config, "workload": workload,
                    "workload_hash": hashlib.sha256(json.dumps(workload, sort_keys=True).encode()).hexdigest()}
        checker_files = [Path(__file__).parent / path for path in
            ("evaluators/html_eval.py", "evaluators/execution_smoke.py", "behavior/browser.py", "behavior/checks.py",
             "behavior/models.py", "behavior/suite.py", "core/result.py", "core/layered_report.py")]
        metadata["checker_hash"] = hashlib.sha256(b"".join(str(path.relative_to(Path(__file__).parent)).encode() + b"\0" + path.read_bytes() + b"\0" for path in checker_files)).hexdigest()
        metadata["runtime"] = {"python": platform.python_version(), "playwright": importlib.metadata.version("playwright")}
        layers = build_layer_report(results, metadata)
        (pending / "layers.json").write_text(json.dumps(layers, indent=2), encoding="utf-8")
        (pending / "report.md").write_text(markdown_layer_report(layers), encoding="utf-8")
        (pending / "run.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        destination = pending.rename(output_dir / run_id)
    except (OSError, ValueError) as exc:
        raise click.ClickException(f"Run could not be completed ({type(exc).__name__})") from None
    click.echo(f"Reports: {destination}")
    click.echo(f"Structural passes: {sum(r.passed and not r.error for r in results)}/{len(results)}")
    for layer in ("smoke", "behavior"):
        summary = layers["summary"][layer]
        click.echo(f"{layer.capitalize()}: {summary['passed']} passed / {summary['judged']} judged; "
                   f"{summary['checker_error']} checker errors, {summary['not_run']} not run, {summary['not_applicable']} not applicable")
    if any(requested_checks_failed(r) for r in results):
        raise click.exceptions.Exit(1)


@main.command()
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), default=Path("reports/runs"))
@click.pass_context
def demo(context, output_dir):
    """Run the five packaged reference fixtures in Chromium without API calls."""
    click.echo("Hand-written checker references; not model-generated outputs or model-quality measurements.")
    context.invoke(run, target="artifacts", suite=SUITE_NAME, artifacts_dir=SUITE_ROOT / "fixtures",
                   case_ids=(), output_dir=output_dir)


if __name__ == "__main__":
    main()
