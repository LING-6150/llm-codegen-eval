"""Create GitHub issues that document the staged eval-harness roadmap.

Usage:
    GITHUB_TOKEN=... uv run python scripts/create_github_issues.py --repo LING-6150/llm-codegen-eval

By default the script does a dry run. Add --apply to create issues. Completed
historical tasks are created and then immediately closed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


DEFAULT_REPO = "LING-6150/llm-codegen-eval"


@dataclass(frozen=True)
class IssueSpec:
    title: str
    state: str
    body: str


def issue_body(
    goal: str,
    context: str,
    implementation: list[str],
    validation: list[str],
    result: str,
    links: list[str],
) -> str:
    return "\n".join(
        [
            "## Goal",
            "",
            goal,
            "",
            "## Context",
            "",
            context,
            "",
            "## Implementation",
            "",
            *[f"- [x] {item}" for item in implementation],
            "",
            "## Validation",
            "",
            *[f"- {item}" for item in validation],
            "",
            "## Result",
            "",
            result,
            "",
            "## Links",
            "",
            *[f"- {item}" for item in links],
        ]
    )


def open_issue_body(
    goal: str,
    context: str,
    implementation: list[str],
    validation: list[str],
    result: str,
    links: list[str],
) -> str:
    return "\n".join(
        [
            "## Goal",
            "",
            goal,
            "",
            "## Context",
            "",
            context,
            "",
            "## Implementation",
            "",
            *[f"- [ ] {item}" for item in implementation],
            "",
            "## Validation",
            "",
            *[f"- [ ] {item}" for item in validation],
            "",
            "## Expected Result",
            "",
            result,
            "",
            "## Links",
            "",
            *[f"- {item}" for item in links],
        ]
    )


ISSUES = [
    IssueSpec(
        title="Day 1: Build project skeleton and single-case HTML eval pipeline",
        state="closed",
        body=issue_body(
            goal="Create an independent Python eval harness repo that can call the Java AI code generation service and evaluate one generated HTML case end to end.",
            context="This established the foundation for answering the interview question: how do we know the multi-agent codegen system is good?",
            implementation=[
                "Scaffold Python package structure",
                "Define core EvalCase and EvalResult models",
                "Add Java service SSE client",
                "Implement first HTML evaluator path",
            ],
            validation=[
                "Ran single-case smoke flow against the local Java service",
                "Confirmed generated code can be evaluated and serialized as EvalResult",
            ],
            result="The repo had a working end-to-end path from prompt to Java generation to evaluator result.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/05198a7",
            ],
        ),
    ),
    IssueSpec(
        title="Day 2: Add benchmark case schema and 30 evaluation cases",
        state="closed",
        body=issue_body(
            goal="Create a HumanEval/SWE-bench-inspired case bank for HTML, multi-file, and Vue project generation tasks.",
            context="The project needed realistic engineering prompts instead of one-off demos, so baseline numbers would be meaningful enough for resume and interview discussion.",
            implementation=[
                "Add 30 JSON EvalCase definitions",
                "Cover HTML, multi-file, and Vue project code types",
                "Include required, optional, and forbidden checks",
                "Annotate cases by difficulty",
            ],
            validation=[
                "Loaded cases through the benchmark harness",
                "Checked case schema compatibility with the evaluator pipeline",
            ],
            result="The eval harness gained a structured benchmark set for repeatable experiments.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/3126194",
            ],
        ),
    ),
    IssueSpec(
        title="Day 3: Add batch runner, markdown reporter, and CLI workflow",
        state="closed",
        body=issue_body(
            goal="Support running a filtered set of cases and producing a readable benchmark report.",
            context="A three-minute interview demo needs one command that runs a baseline and emits a report, not a collection of manual scripts.",
            implementation=[
                "Add batch runner over EvalCase lists",
                "Save raw EvalResult JSON",
                "Generate markdown reports with summary and per-case details",
                "Expose a CLI entry point for benchmark runs",
            ],
            validation=[
                "Ran smoke benchmark reports",
                "Generated baseline HTML and multi-file raw result artifacts",
            ],
            result="The project became demoable through a repeatable CLI benchmark command.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/9315ab1",
                "Local reports: reports/raw_baseline_html_20260527_153226.json, reports/raw_baseline_multi_20260527_165814.json",
            ],
        ),
    ),
    IssueSpec(
        title="Day 4A: Tune brittle selector checks from baseline failure analysis",
        state="closed",
        body=issue_body(
            goal="Reduce false negatives caused by overly strict selector and text checks in baseline cases.",
            context="The eval harness should measure generated application behavior, not fail good generations because the case expected exactly one implementation detail.",
            implementation=[
                "Review baseline failure patterns",
                "Loosen brittle checks using regex and alternate selectors",
                "Preserve semantic intent of each case",
            ],
            validation=[
                "Compared changes against baseline failure analysis",
                "Deferred full batch rerun to the next unified benchmark step",
            ],
            result="Several baseline checks became more robust while keeping the same user-facing expectations.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/30584d5",
            ],
        ),
    ),
    IssueSpec(
        title="Day 4B: Add pass@k support for repeated generations",
        state="closed",
        body=issue_body(
            goal="Support HumanEval-style repeated runs per case and calculate pass@k.",
            context="Code generation is stochastic; one run per case is useful for pass@1, but pass@k shows stability and retry value.",
            implementation=[
                "Add --runs-per-case to benchmark runners",
                "Store multiple EvalResult records per case",
                "Compute pass@k and stability by case",
                "Show stability in markdown reports",
            ],
            validation=[
                "Added unit tests for pass@k and stability logic",
                "Ran the test suite",
            ],
            result="The harness can now report pass@1 and pass@k from the same raw result structure.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/12e35c5",
            ],
        ),
    ),
    IssueSpec(
        title="Day 4C: Add chat_history cleanup preflight",
        state="closed",
        body=issue_body(
            goal="Prevent previous generation history from polluting benchmark runs.",
            context="The Java service stores chat history by appId, so repeated eval runs could accidentally include stale context unless cleaned before each case.",
            implementation=[
                "Add MySQL chat_history cleanup hook",
                "Run cleanup before each case run",
                "Support MySQL credentials through CLI/env",
                "Fail early if cleanup cannot be verified",
            ],
            validation=[
                "Added preflight tests",
                "Used cleanup during subsequent A/B benchmark runs",
            ],
            result="Each case run starts from a clean chat_history state for the configured appId.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/12e35c5",
            ],
        ),
    ),
    IssueSpec(
        title="Day 5: Add A/B benchmark runner for config comparisons",
        state="closed",
        body=issue_body(
            goal="Run two Java service configurations against the same cases and produce a diff report.",
            context="This is the infrastructure needed to compare multi-agent vs single-agent, and later pruning on vs off.",
            implementation=[
                "Add YAML run configs",
                "Add scripts/run_ab.py",
                "Pass Java request params through the client",
                "Generate markdown A/B reports",
            ],
            validation=[
                "Ran unit tests",
                "Generated A/B comparison reports from raw results",
            ],
            result="The harness can compare two variants with pass-rate, score, duration, improvements, and regressions.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/a98bded",
            ],
        ),
    ),
    IssueSpec(
        title="Day 5.5: Harden A/B reporting and comparison workflow",
        state="closed",
        body=issue_body(
            goal="Make A/B reports reliable for limited runs, raw-result comparisons, and smoke debugging.",
            context="Small smoke runs and partially completed raw files should still produce accurate reports without listing unrelated cases.",
            implementation=[
                "Fix limited raw result comparison",
                "Avoid duplicate pass@1 rows",
                "Improve report metadata",
                "Add regression/improvement/unstable case sections",
            ],
            validation=[
                "Ran A/B reporter tests",
                "Regenerated smoke comparison reports",
            ],
            result="A/B reports became stable enough for pruning smoke runs and future experiment writeups.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/77b377c",
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/d8abc87",
            ],
        ),
    ),
    IssueSpec(
        title="Day 6A: Add context pruning switch to Java generation service",
        state="closed",
        body=issue_body(
            goal="Add a runtime switch for field-level context pruning in the multi-agent Java code generation workflow.",
            context="This is the core AgentPrune-inspired intervention: downstream agents should receive only the context fields they need.",
            implementation=[
                "Add contextPruning request parameter support",
                "Thread pruning state through AgentContext",
                "Apply pruning rules before downstream agent calls",
                "Keep old Java API constructors compatible",
            ],
            validation=[
                "Ran targeted Java tests",
                "Ran Java compile",
                "Verified eval config passes contextPruning true/false",
            ],
            result="The Java service can run the same workflow with pruning enabled or disabled.",
            links=[
                "Eval commit: https://github.com/LING-6150/llm-codegen-eval/commit/26f980f",
                "Java commit: https://github.com/LING-6150/ling-ai-generation-engine/commit/87ede54",
            ],
        ),
    ),
    IssueSpec(
        title="Day 6.5: Retry transient provider and network infra failures",
        state="closed",
        body=issue_body(
            goal="Automatically retry transient LLM provider failures without hiding real eval failures.",
            context="DeepSeek occasionally returns TLS handshake/network errors. Those should not be mistaken for pruning regressions.",
            implementation=[
                "Detect transient infra error markers",
                "Add --infra-retries",
                "Retry only infra errors",
                "Run chat_history cleanup before retry attempts",
            ],
            validation=[
                "Added unit tests for retry behavior",
                "Used retries in formal pruning A/B runs",
            ],
            result="The benchmark is more resilient while still preserving real case failures.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/05e7c7d",
            ],
        ),
    ),
    IssueSpec(
        title="Day 6B: Run pruning smoke and formal pass@1 A/B benchmark",
        state="closed",
        body=issue_body(
            goal="Validate pruning on/off end to end against Multi-File cases.",
            context="Before claiming pruning works, the harness needed a real A/B run through Java, MySQL cleanup, raw result saving, and markdown reporting.",
            implementation=[
                "Run smoke A/B for pruning_off vs pruning_on",
                "Run formal 10-case Multi-File A/B",
                "Record raw result files and report paths",
                "Document TLS/network caveats",
            ],
            validation=[
                "Formal command: EVAL_MYSQL_PASSWORD=... uv run python scripts/run_ab.py --config-a configs/pruning_off.yaml --config-b configs/pruning_on.yaml --type multi_file --runs-per-case 1 --infra-retries 1",
            ],
            result="Formal run preserved pass@1 at 90.0% with no pass/fail regressions. Token reduction was not claimable yet in this run.",
            links=[
                "Local report: reports/ab_pruning_off_vs_pruning_on_20260529_222047.md",
            ],
        ),
    ),
    IssueSpec(
        title="Day 6C: Capture Prometheus token deltas for pruning A/B",
        state="closed",
        body=issue_body(
            goal="Measure token usage for pruning off vs on without changing Java metric labels.",
            context="The resume claim needs real token reduction data. Since Prometheus counters are cumulative, the eval harness snapshots counters before and after each sequential config run.",
            implementation=[
                "Add Prometheus metric parser",
                "Extract ai_model_tokens_total by appId",
                "Compute before/after deltas by config",
                "Add Token Usage section to A/B reports",
                "Rerun formal pruning A/B with token capture",
            ],
            validation=[
                "uv run pytest: 17 passed",
                "Formal 10-case Multi-File A/B rerun completed",
            ],
            result="Context pruning reduced measured model tokens by 7.0% while preserving pass@1 at 90.0%.",
            links=[
                "Commit: https://github.com/LING-6150/llm-codegen-eval/commit/9fb0bd3",
                "Local report: reports/ab_pruning_off_vs_pruning_on_20260530_000411.md",
            ],
        ),
    ),
    IssueSpec(
        title="Day 7: Run pass@3 pruning stability experiment",
        state="open",
        body=open_issue_body(
            goal="Repeat pruning off vs on with runs_per_case=3 to measure pass@3 and stability.",
            context="The current pruning result is pass@1. A pass@3 run would better show stochastic stability, but costs roughly 3x runtime.",
            implementation=[
                "Choose full 10-case Multi-File run or smaller representative subset",
                "Run pruning_off vs pruning_on with --runs-per-case 3",
                "Use --infra-retries 1 and token metrics capture",
                "Compare pass@1, pass@3, run-level pass rate, score, latency, and token delta",
            ],
            validation=[
                "Save raw result JSON for both configs",
                "Generate markdown A/B report",
                "Update EVAL_HARNESS_NOTES.md with real metrics",
            ],
            result="A stability-backed pruning result that can be cited more confidently than one pass@1 run.",
            links=[
                "Related issue: Day 6C token delta",
            ],
        ),
    ),
    IssueSpec(
        title="Day 8: Implement VueEvaluator for vue_project cases",
        state="open",
        body=open_issue_body(
            goal="Evaluate Vue project generations instead of leaving Vue cases unrunnable.",
            context="The case bank includes Vue project cases, but the harness currently lacks a dedicated Vue evaluator.",
            implementation=[
                "Define expected generated project layout",
                "Install or reuse a lightweight Vue build/test strategy",
                "Evaluate required text/component/style checks",
                "Handle build failures as EvalResult errors",
            ],
            validation=[
                "Run Vue smoke cases",
                "Run all vue_project cases",
                "Add unit tests around evaluator behavior",
            ],
            result="Vue cases can contribute to baseline and A/B reports.",
            links=[
                "Roadmap: EVAL_HARNESS_NOTES.md",
            ],
        ),
    ),
    IssueSpec(
        title="Day 9: Add Resilience4j fallback chain for provider TLS failures",
        state="open",
        body=open_issue_body(
            goal="Reduce benchmark disruption from DeepSeek TLS/network errors at the Java service layer.",
            context="Eval-level retry helps, but production workflow should eventually have provider fallback/circuit breaker behavior.",
            implementation=[
                "Identify model call boundary in Java service",
                "Add Resilience4j retry/circuit breaker configuration",
                "Define fallback model/provider policy",
                "Expose fallback metadata in logs or metrics",
            ],
            validation=[
                "Unit/integration test transient provider failure path",
                "Run eval smoke with induced or observed TLS failures",
                "Confirm raw reports distinguish provider fallback from eval failure",
            ],
            result="Provider instability becomes observable and recoverable instead of randomly failing eval cases.",
            links=[
                "Observed issue: DeepSeek TLS handshake failures during Day 6B smoke",
            ],
        ),
    ),
    IssueSpec(
        title="Day 10: Add GitHub Actions smoke eval",
        state="open",
        body=open_issue_body(
            goal="Run a lightweight CI check on push without requiring the full Java service benchmark.",
            context="The repo should show engineering hygiene, but full LLM evals are too slow and environment-dependent for every push.",
            implementation=[
                "Add pytest workflow",
                "Add offline smoke tests for parser/reporter/config logic",
                "Optionally add a mocked Java client smoke path",
                "Document why live LLM benchmark is manual",
            ],
            validation=[
                "GitHub Actions passes on main",
                "Local uv run pytest remains green",
            ],
            result="The public repo has CI confidence without pretending live LLM evaluation is deterministic or cheap.",
            links=[
                "Roadmap: EVAL_HARNESS_NOTES.md",
            ],
        ),
    ),
    IssueSpec(
        title="Day 11: Rewrite README for production-style demo",
        state="open",
        body=open_issue_body(
            goal="Turn the README into a clear portfolio entry for recruiters and interviewers.",
            context="The current project is technically strong; the README should make the purpose, architecture, metrics, and demo path obvious in under three minutes.",
            implementation=[
                "Add project positioning and architecture diagram",
                "Add quickstart commands",
                "Add benchmark result table",
                "Add pruning experiment summary",
                "Add caveats around real LLM infra instability",
            ],
            validation=[
                "Follow the README from a clean checkout",
                "Confirm all referenced commands and report paths are accurate",
            ],
            result="A recruiter/interviewer can understand the eval harness and the pruning result without reading all source files.",
            links=[
                "Current pruning result: token -7.0%, pass@1 unchanged at 90.0%",
            ],
        ),
    ),
    IssueSpec(
        title="Day 12: Create three-minute interview demo script",
        state="open",
        body=open_issue_body(
            goal="Prepare a concise demo flow that shows baseline, A/B report, and pruning result.",
            context="The project goal includes an interview moment where the interviewer says: show me. The demo should be fast, concrete, and honest.",
            implementation=[
                "Write demo script with exact terminal commands",
                "Identify pre-generated reports to show when live LLM calls are too slow",
                "Add talking points for eval design and pruning caveats",
                "Add troubleshooting notes for MySQL, Java service, and TLS errors",
            ],
            validation=[
                "Rehearse demo in under three minutes",
                "Confirm all report links/paths exist",
            ],
            result="A repeatable demo narrative for North America AI application engineering interviews.",
            links=[
                "Related: README production rewrite",
            ],
        ),
    ),
]


class GitHubClient:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.token = token
        self.base_url = f"https://api.github.com/repos/{repo}"

    def list_issues(self) -> list[dict]:
        return self._request("GET", f"{self.base_url}/issues?state=all&per_page=100")

    def create_issue(self, spec: IssueSpec) -> dict:
        return self._request(
            "POST",
            f"{self.base_url}/issues",
            {"title": spec.title, "body": spec.body},
        )

    def close_issue(self, issue_number: int) -> dict:
        return self._request(
            "PATCH",
            f"{self.base_url}/issues/{issue_number}",
            {"state": "closed"},
        )

    def _request(self, method: str, url: str, payload: dict | None = None) -> dict | list[dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "llm-codegen-eval-issue-importer",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise RuntimeError(f"GitHub API {method} {url} failed: {exc.code} {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Create staged roadmap issues on GitHub")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo, default: LING-6150/llm-codegen-eval")
    parser.add_argument("--apply", action="store_true", help="Actually create issues. Default is dry-run.")
    args = parser.parse_args()

    if not args.apply:
        print(f"Dry run for {args.repo}: {len(ISSUES)} issues")
        for spec in ISSUES:
            print(f"- [{spec.state}] {spec.title}")
        print("\nAdd --apply with GITHUB_TOKEN set to create them.")
        return 0

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN or GH_TOKEN is required when using --apply.", file=sys.stderr)
        return 2

    client = GitHubClient(args.repo, token)
    existing = {issue["title"]: issue for issue in client.list_issues()}

    for spec in ISSUES:
        if spec.title in existing:
            issue = existing[spec.title]
            print(f"skip existing #{issue['number']}: {spec.title}")
            continue
        created = client.create_issue(spec)
        print(f"created #{created['number']}: {spec.title}")
        if spec.state == "closed":
            client.close_issue(created["number"])
            print(f"closed #{created['number']}: {spec.title}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
