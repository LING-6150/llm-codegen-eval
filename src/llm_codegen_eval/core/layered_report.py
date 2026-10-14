"""Independent layer accounting; never turn checker errors into model failures."""
from collections import Counter
from html import escape
import re
from urllib.parse import quote

STATUSES = ("passed", "failed", "checker_error", "not_run", "not_applicable")


def layer_states(result):
    generation_failed = bool(result.error and result.error.startswith("Generation failed:"))
    structural = "not_run" if generation_failed else ("checker_error" if result.error else ("passed" if result.passed else "failed"))
    smoke = result.execution_smoke
    smoke_status = "not_run"
    if smoke is not None:
        smoke_status = ("not_applicable" if not smoke.applicable else
                        "passed" if smoke.passed else
                        "checker_error" if smoke.failure_type == "checker_error" else "failed")
    behavior = result.behavior_result
    behavior_status = behavior.status if behavior else ("not_run" if result.run_config.get("behavior_enabled") else "not_applicable")
    return {"structural": structural, "smoke": smoke_status, "behavior": behavior_status}


def build_layer_report(results, run_metadata):
    rows = []
    for result in results:
        rows.append({"case_id": result.case_id, "run_index": result.run_config.get("run_index", 1),
            "layers": layer_states(result), "structural_score": result.score,
            "generation_error": result.error, "artifact": result.generated_artifact_path,
            "artifact_sha256": result.run_config.get("artifact_sha256"),
            "smoke": result.execution_smoke.model_dump(mode="json") if result.execution_smoke else None,
            "behavior": result.behavior_result.model_dump(mode="json") if result.behavior_result else None,
            "evidence": result.browser_evidence, "browser_diagnostics": result.browser_diagnostics})
    summary = {}
    for layer in ("structural", "smoke", "behavior"):
        counts = Counter(row["layers"][layer] for row in rows)
        judged = counts["passed"] + counts["failed"]
        summary[layer] = {**{s: counts[s] for s in STATUSES}, "judged": judged,
                          "pass_rate": counts["passed"] / judged if judged else None}
    return {"schema_version": 1, "run_id": run_metadata["run_id"],
            "source_kind": run_metadata["source_kind"], "suite": run_metadata["suite"],
            "workload_hash": run_metadata["workload_hash"],
            "checker_hash": run_metadata["checker_hash"], "attempts": len(rows),
            "generation_errors": sum(bool(r.error and r.error.startswith("Generation failed:")) for r in results),
            "summary": summary, "results": rows}


def safe_text(value):
    text = escape(str(value)).replace("\n", " ")
    return re.sub(r"([\\`*_[\]{}|])", r"\\\1", text)


def artifact_link(label, path):
    return f"[{label}]({quote(path, safe='/')})"


def markdown_layer_report(report):
    lines = ["# HTML evaluation — three independent layers", "",
             f"Suite: {safe_text(report['suite'])}", f"Source: {safe_text(report['source_kind'])}", ""]
    if report["source_kind"] == "artifact-replay":
        lines += ["**Saved-artifact replay; not a live model benchmark.**", ""]
    lines += [f"Attempts: {report['attempts']}; generation errors: {report['generation_errors']}.", "",
              "Pass rates use passed / (passed + failed) within each layer. Checker errors, not-run and",
              "not-applicable attempts are excluded from that rate and shown separately. Read coverage with the rate.",
              "There is no combined score or implied full functional correctness.", "",
              "| Layer | Passed | Failed | Checker errors | Not run | Not applicable | Judged | Pass rate |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for layer, summary in report["summary"].items():
        rate = f"{summary['pass_rate']:.1%}" if summary["pass_rate"] is not None else "N/A"
        lines.append(f"| {layer} | {summary['passed']} | {summary['failed']} | {summary['checker_error']} | {summary['not_run']} | {summary['not_applicable']} | {summary['judged']} | {rate} |")
    lines += ["", "## Per-attempt outcomes", "",
              "| Case | Attempt | Structural | Smoke | Behavior | Artifact / browser evidence |",
              "|---|---:|---|---|---|---|"]
    for row in report["results"]:
        evidence = []
        if row["artifact"]:
            evidence.append(artifact_link("HTML", row["artifact"]))
        evidence.extend(artifact_link(key, path) for key, path in row["evidence"].items())
        state = row["layers"]
        lines.append(f"| {safe_text(row['case_id'])} | {row['run_index']} | {state['structural']} | {state['smoke']} | {state['behavior']} | {' · '.join(evidence)} |")
    lines += ["", "## Failures, unavailable checks and evidence errors", ""]
    details = []
    for row in report["results"]:
        prefix = f"{safe_text(row['case_id'])} / attempt {row['run_index']}"
        if row["generation_error"]:
            details.append(f"- {prefix}: {safe_text(row['generation_error'])}")
        if row["layers"]["structural"] == "failed":
            details.append(f"- {prefix}: structural requirements failed; see results.json for failed checks.")
        if row["smoke"] and not row["smoke"]["passed"]:
            details.append(f"- {prefix}: smoke {safe_text(row['smoke']['failure_type'])}: {safe_text(row['smoke']['detail'])}")
        if row["behavior"]:
            behavior = row["behavior"]
            if behavior["detail"]:
                details.append(f"- {prefix}: behavior {behavior['status']}: {safe_text(behavior['detail'])}")
            for check in behavior["checks"]:
                if check["status"] != "passed":
                    details.append(f"- {prefix}: **{safe_text(check['check_id'])}** — {check['status']}: {safe_text((check['detail'] or '')[:700])}")
        for detail in row["browser_diagnostics"].get("evidence_errors", []):
            details.append(f"- {prefix}: evidence capture error: {safe_text(detail)}")
    lines += details or ["No failures recorded in the requested checks."]
    lines += ["", "## Provenance", "", f"Workload SHA-256: `{report['workload_hash']}`",
              f"Checker SHA-256: `{report['checker_hash']}`", "",
              "Complete HTML is retained in artifacts/. Raw result fields `passed` and `score` keep their",
              "historical structural-only meaning. See run.json for parameters and runtime versions.", ""]
    return "\n".join(lines)


def requested_checks_failed(result):
    statuses = layer_states(result)
    return bool(result.error or any(s in {"failed", "checker_error"} for s in statuses.values()) or
                result.browser_diagnostics.get("evidence_errors"))
