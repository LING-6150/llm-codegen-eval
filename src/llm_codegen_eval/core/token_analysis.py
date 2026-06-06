"""Offline token attribution analysis for saved A/B raw results."""

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median
from typing import Any

from .batch_runner import is_infra_error
from .result import EvalResult
from .stats import results_by_case


EXCLUSION_REASONS = (
    "infra_error",
    "other_generation_error",
    "token_capture_error",
    "missing_token_summary",
)


@dataclass(frozen=True)
class AgentTokens:
    input: float
    output: float
    total: float


@dataclass(frozen=True)
class TokenMeans:
    input: float
    output: float
    total: float
    by_agent: dict[str, AgentTokens]
    n_runs: int


@dataclass(frozen=True)
class AgentDelta:
    input: float
    output: float
    total: float


@dataclass(frozen=True)
class CaseTokenComparison:
    case_id: str
    a: TokenMeans | None
    b: TokenMeans | None
    paired: bool
    delta_total: float | None
    delta_total_pct: float | None
    delta_input: float | None
    delta_output: float | None
    delta_by_agent: dict[str, AgentDelta]


@dataclass(frozen=True)
class AgentAggregate:
    agent: str
    n_cases: int
    a_mean_total: float
    b_mean_total: float
    delta_total_pct: float | None
    a_mean_input: float
    b_mean_input: float
    delta_input_pct: float | None


@dataclass(frozen=True)
class IOSplit:
    a_input: float
    b_input: float
    input_delta_pct: float | None
    a_output: float
    b_output: float
    output_delta_pct: float | None
    a_total: float
    b_total: float
    total_delta_pct: float | None


@dataclass(frozen=True)
class PairedDirectionSummary:
    n_paired_cases: int
    n_delta_pct_cases: int
    cases_b_higher: int
    cases_b_lower: int
    cases_equal: int
    mean_delta_pct: float | None
    median_delta_pct: float | None
    min_delta_pct: float | None
    max_delta_pct: float | None
    directional_only: bool


@dataclass(frozen=True)
class MechanismMeans:
    requests_started: float
    prompt_chars: float
    input_tokens: float
    mean_prompt_chars_per_request: float | None
    input_tokens_per_request: float | None
    n_runs: int


@dataclass(frozen=True)
class CaseMechanismComparison:
    case_id: str
    a: MechanismMeans | None
    b: MechanismMeans | None
    paired: bool
    mechanism: str


@dataclass(frozen=True)
class ArmValidity:
    name: str
    total_runs: int
    valid_token_runs: int
    excluded: dict[str, int]
    valid_token_sum: int
    accounted_token_sum: int
    config_token_total: int | None
    cross_check_match: bool | None
    cross_check_diff: int | None


@dataclass(frozen=True)
class ExcludedRun:
    case_id: str
    arm: str
    run_index: int
    reason: str
    detail: str | None


@dataclass(frozen=True)
class UnpairedCase:
    case_id: str
    present_in: str
    reason: str


@dataclass(frozen=True)
class TokenAttributionAnalysis:
    name_a: str
    name_b: str
    per_case: list[CaseTokenComparison]
    paired_case_ids: list[str]
    unpaired_cases: list[UnpairedCase]
    by_agent: list[AgentAggregate]
    io_split: IOSplit
    direction: PairedDirectionSummary
    codegen_mechanism: list[CaseMechanismComparison]
    validity_a: ArmValidity
    validity_b: ArmValidity
    excluded_runs: list[ExcludedRun]
    caveats: list[str]


def analyze_token_attribution(
    results_a: list[EvalResult],
    results_b: list[EvalResult],
    name_a: str = "pruning_off",
    name_b: str = "pruning_on",
    config_token_summary_a: dict[str, Any] | None = None,
    config_token_summary_b: dict[str, Any] | None = None,
) -> TokenAttributionAnalysis:
    """Analyze per-run token summaries from two saved A/B result sets."""
    excluded_runs: list[ExcludedRun] = []
    valid_a, validity_a = _valid_results_by_case(
        results_a,
        name_a,
        _config_total(config_token_summary_a),
        excluded_runs,
    )
    valid_b, validity_b = _valid_results_by_case(
        results_b,
        name_b,
        _config_total(config_token_summary_b),
        excluded_runs,
    )

    raw_case_ids_a = set(results_by_case(results_a))
    raw_case_ids_b = set(results_by_case(results_b))
    valid_case_ids_a = set(valid_a)
    valid_case_ids_b = set(valid_b)
    all_case_ids = sorted(raw_case_ids_a | raw_case_ids_b | valid_case_ids_a | valid_case_ids_b)

    per_case: list[CaseTokenComparison] = []
    paired_case_ids: list[str] = []
    unpaired_cases: list[UnpairedCase] = []
    for case_id in all_case_ids:
        means_a = _token_means(valid_a.get(case_id, []))
        means_b = _token_means(valid_b.get(case_id, []))
        comparison = _case_comparison(case_id, means_a, means_b)
        per_case.append(comparison)
        if comparison.paired:
            paired_case_ids.append(case_id)
        else:
            unpaired = _unpaired_case(
                case_id,
                means_a,
                means_b,
                case_id in raw_case_ids_a,
                case_id in raw_case_ids_b,
            )
            if unpaired is not None:
                unpaired_cases.append(unpaired)

    paired_cases = [case for case in per_case if case.paired]
    codegen_mechanism = [
        _case_mechanism_comparison(
            case_id,
            _mechanism_means(valid_a.get(case_id, []), "CodeGenAgent"),
            _mechanism_means(valid_b.get(case_id, []), "CodeGenAgent"),
        )
        for case_id in all_case_ids
    ]
    analysis = TokenAttributionAnalysis(
        name_a=name_a,
        name_b=name_b,
        per_case=per_case,
        paired_case_ids=paired_case_ids,
        unpaired_cases=unpaired_cases,
        by_agent=_agent_aggregates(paired_cases),
        io_split=_io_split(paired_cases),
        direction=_direction_summary(paired_cases),
        codegen_mechanism=codegen_mechanism,
        validity_a=validity_a,
        validity_b=validity_b,
        excluded_runs=excluded_runs,
        caveats=_caveats(paired_case_ids, validity_a, validity_b, unpaired_cases),
    )
    return analysis


def render_token_attribution_markdown(analysis: TokenAttributionAnalysis) -> str:
    """Render token attribution analysis as a compact markdown report."""
    lines = [
        f"# Token Attribution Analysis - {analysis.name_a} vs {analysis.name_b}",
        "",
        "**Unit of analysis**: per-case mean of valid runs. Runs are not treated as independent samples.",
        "**Statistical claim**: directional only; no p-values, confidence intervals, or significance claims.",
        "",
    ]

    if analysis.caveats:
        lines.append("## Caveats")
        lines.append("")
        for caveat in analysis.caveats:
            lines.append(f"- {caveat}")
        lines.append("")

    lines.append("## Per-Case Token Comparison")
    lines.append("")
    lines.append("| Case | A Total | B Total | Delta | Delta % | A CodeGen Input | B CodeGen Input | CodeGen Input Delta % |")
    lines.append("|------|---------|---------|-------|---------|-----------------|-----------------|-----------------------|")
    for case in analysis.per_case:
        codegen_a = _agent_input(case.a, "CodeGenAgent")
        codegen_b = _agent_input(case.b, "CodeGenAgent")
        lines.append(
            "| "
            f"{case.case_id} | "
            f"{_fmt_float(_means_total(case.a))} | "
            f"{_fmt_float(_means_total(case.b))} | "
            f"{_fmt_float(case.delta_total, signed=True)} | "
            f"{_fmt_pct(case.delta_total_pct, signed=True)} | "
            f"{_fmt_float(codegen_a)} | "
            f"{_fmt_float(codegen_b)} | "
            f"{_fmt_pct(_delta_pct(codegen_a, codegen_b), signed=True)} |"
        )
    lines.append("")

    lines.append("## By-Agent Aggregate")
    lines.append("")
    lines.append("| Agent | Paired Cases | A Total | B Total | Delta % | A Input | B Input | Input Delta % |")
    lines.append("|-------|--------------|---------|---------|---------|---------|---------|---------------|")
    for agent in analysis.by_agent:
        lines.append(
            f"| {agent.agent} | {agent.n_cases} | "
            f"{_fmt_float(agent.a_mean_total)} | {_fmt_float(agent.b_mean_total)} | "
            f"{_fmt_pct(agent.delta_total_pct, signed=True)} | "
            f"{_fmt_float(agent.a_mean_input)} | {_fmt_float(agent.b_mean_input)} | "
            f"{_fmt_pct(agent.delta_input_pct, signed=True)} |"
        )
    lines.append("")

    lines.append("## Input / Output Split")
    lines.append("")
    lines.append("| Metric | A | B | Delta % |")
    lines.append("|--------|---|---|---------|")
    lines.append(
        f"| Input | {_fmt_float(analysis.io_split.a_input)} | "
        f"{_fmt_float(analysis.io_split.b_input)} | "
        f"{_fmt_pct(analysis.io_split.input_delta_pct, signed=True)} |"
    )
    lines.append(
        f"| Output | {_fmt_float(analysis.io_split.a_output)} | "
        f"{_fmt_float(analysis.io_split.b_output)} | "
        f"{_fmt_pct(analysis.io_split.output_delta_pct, signed=True)} |"
    )
    lines.append(
        f"| Total | {_fmt_float(analysis.io_split.a_total)} | "
        f"{_fmt_float(analysis.io_split.b_total)} | "
        f"{_fmt_pct(analysis.io_split.total_delta_pct, signed=True)} |"
    )
    lines.append("")

    lines.append("## CodeGen Mechanism")
    lines.append("")
    lines.append(
        "| Case | A Requests | B Requests | A Prompt Chars/Req | B Prompt Chars/Req | "
        "A Input Tokens/Req | B Input Tokens/Req | Mechanism |"
    )
    lines.append(
        "|------|------------|------------|--------------------|--------------------|"
        "--------------------|--------------------|-----------|"
    )
    for case in analysis.codegen_mechanism:
        lines.append(
            "| "
            f"{case.case_id} | "
            f"{_fmt_float(_mechanism_requests(case.a))} | "
            f"{_fmt_float(_mechanism_requests(case.b))} | "
            f"{_fmt_float(_mechanism_prompt_per_request(case.a))} | "
            f"{_fmt_float(_mechanism_prompt_per_request(case.b))} | "
            f"{_fmt_float(_mechanism_input_per_request(case.a))} | "
            f"{_fmt_float(_mechanism_input_per_request(case.b))} | "
            f"{case.mechanism} |"
        )
    lines.append("")

    lines.append("## Paired Direction Summary")
    lines.append("")
    lines.append("| Paired Cases | Delta % Cases | B Higher | B Lower | Equal | Mean Delta % | Median Delta % | Range |")
    lines.append("|--------------|---------------|----------|---------|-------|--------------|----------------|-------|")
    direction = analysis.direction
    lines.append(
        f"| {direction.n_paired_cases} | {direction.n_delta_pct_cases} | {direction.cases_b_higher} | "
        f"{direction.cases_b_lower} | {direction.cases_equal} | "
        f"{_fmt_pct(direction.mean_delta_pct, signed=True)} | "
        f"{_fmt_pct(direction.median_delta_pct, signed=True)} | "
        f"{_fmt_pct(direction.min_delta_pct, signed=True)} to {_fmt_pct(direction.max_delta_pct, signed=True)} |"
    )
    lines.append("")

    lines.append("## Validity & Cross-Check")
    lines.append("")
    lines.append("| Arm | Total Runs | Valid Token Runs | Excluded | Valid Token Sum | Accounted Token Sum | Config Token Total | Cross-Check |")
    lines.append("|-----|------------|------------------|----------|-----------------|---------------------|--------------------|-------------|")
    for validity in (analysis.validity_a, analysis.validity_b):
        lines.append(
            f"| {validity.name} | {validity.total_runs} | {validity.valid_token_runs} | "
            f"{_format_excluded(validity.excluded)} | "
            f"{validity.valid_token_sum:,} | {validity.accounted_token_sum:,} | "
            f"{_fmt_int(validity.config_token_total)} | {_format_cross_check(validity)} |"
        )
    lines.append("")

    if analysis.unpaired_cases:
        lines.append("## Unpaired Cases")
        lines.append("")
        lines.append("| Case | Present In | Reason |")
        lines.append("|------|------------|--------|")
        for case in analysis.unpaired_cases:
            lines.append(f"| {case.case_id} | {case.present_in} | {case.reason} |")
        lines.append("")

    if analysis.excluded_runs:
        lines.append("## Excluded Runs")
        lines.append("")
        lines.append("| Arm | Case | Run | Reason | Detail |")
        lines.append("|-----|------|-----|--------|--------|")
        for run in analysis.excluded_runs:
            lines.append(
                f"| {run.arm} | {run.case_id} | {run.run_index} | "
                f"{run.reason} | {_escape_table(run.detail or '-')} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _valid_results_by_case(
    results: list[EvalResult],
    arm_name: str,
    config_token_total: int | None,
    excluded_runs: list[ExcludedRun],
) -> tuple[dict[str, list[EvalResult]], ArmValidity]:
    valid_by_case: dict[str, list[EvalResult]] = defaultdict(list)
    excluded_counts = {reason: 0 for reason in EXCLUSION_REASONS}
    valid_token_sum = 0
    accounted_token_sum = 0

    for index, result in enumerate(results, start=1):
        accounted_token_sum += int(result.total_tokens or 0)
        accounted_token_sum += _retry_token_sum(result)
        reason = _exclusion_reason(result)
        if reason is None:
            valid_by_case[result.case_id].append(result)
            valid_token_sum += int(result.total_tokens or 0)
            continue

        excluded_counts[reason] += 1
        excluded_runs.append(
            ExcludedRun(
                case_id=result.case_id,
                arm=arm_name,
                run_index=int(result.run_config.get("run_index", index)),
                reason=reason,
                detail=_exclusion_detail(result, reason),
            )
        )

    cross_check_match = None
    cross_check_diff = None
    if config_token_total is not None:
        cross_check_diff = config_token_total - accounted_token_sum
        cross_check_match = cross_check_diff == 0

    validity = ArmValidity(
        name=arm_name,
        total_runs=len(results),
        valid_token_runs=sum(len(case_results) for case_results in valid_by_case.values()),
        excluded=excluded_counts,
        valid_token_sum=valid_token_sum,
        accounted_token_sum=accounted_token_sum,
        config_token_total=config_token_total,
        cross_check_match=cross_check_match,
        cross_check_diff=cross_check_diff,
    )
    return dict(valid_by_case), validity


def _exclusion_reason(result: EvalResult) -> str | None:
    if result.error is not None and is_infra_error(result):
        return "infra_error"
    if result.error is not None:
        return "other_generation_error"
    if "token_capture_error" in result.run_config:
        return "token_capture_error"
    if "token_summary" not in result.run_config:
        return "missing_token_summary"
    return None


def _exclusion_detail(result: EvalResult, reason: str) -> str | None:
    if reason == "token_capture_error":
        return str(result.run_config.get("token_capture_error"))
    if result.error:
        return result.error[:160]
    return None


def _retry_token_sum(result: EvalResult) -> int:
    retry_summaries = result.run_config.get("retry_token_summaries", [])
    if not isinstance(retry_summaries, list):
        return 0
    total = 0
    for summary in retry_summaries:
        if isinstance(summary, dict):
            total += int(summary.get("total", 0) or 0)
    return total


def _token_means(results: list[EvalResult]) -> TokenMeans | None:
    if not results:
        return None

    summaries = [result.run_config["token_summary"] for result in results]
    n_runs = len(summaries)
    agents = sorted(
        {
            agent
            for summary in summaries
            for agent in _summary_by_agent(summary)
        }
    )
    by_agent = {}
    for agent in agents:
        by_agent[agent] = AgentTokens(
            input=_mean_summary_agent(summaries, agent, "input"),
            output=_mean_summary_agent(summaries, agent, "output"),
            total=_mean_summary_agent(summaries, agent, "total"),
        )

    return TokenMeans(
        input=mean(float(summary.get("input", 0) or 0) for summary in summaries),
        output=mean(float(summary.get("output", 0) or 0) for summary in summaries),
        total=mean(float(summary.get("total", 0) or 0) for summary in summaries),
        by_agent=by_agent,
        n_runs=n_runs,
    )


def _mechanism_means(results: list[EvalResult], agent: str) -> MechanismMeans | None:
    agent_summaries = []
    for result in results:
        by_agent = result.run_config.get("mechanism_summary", {}).get("by_agent", {})
        if isinstance(by_agent, dict) and agent in by_agent:
            agent_summaries.append(by_agent[agent])
    if not agent_summaries:
        return None

    requests = mean(float(summary.get("requests_started", 0) or 0) for summary in agent_summaries)
    prompt_chars = mean(float(summary.get("prompt_chars", 0) or 0) for summary in agent_summaries)
    input_tokens = mean(float(summary.get("input_tokens", 0) or 0) for summary in agent_summaries)
    return MechanismMeans(
        requests_started=requests,
        prompt_chars=prompt_chars,
        input_tokens=input_tokens,
        mean_prompt_chars_per_request=_mean_optional(
            summary.get("mean_prompt_chars_per_request") for summary in agent_summaries
        ),
        input_tokens_per_request=_mean_optional(
            summary.get("input_tokens_per_request") for summary in agent_summaries
        ),
        n_runs=len(agent_summaries),
    )


def _case_mechanism_comparison(
    case_id: str,
    means_a: MechanismMeans | None,
    means_b: MechanismMeans | None,
) -> CaseMechanismComparison:
    paired = means_a is not None and means_b is not None
    return CaseMechanismComparison(
        case_id=case_id,
        a=means_a,
        b=means_b,
        paired=paired,
        mechanism=_classify_codegen_mechanism(means_a, means_b) if paired else "unpaired",
    )


def _classify_codegen_mechanism(
    means_a: MechanismMeans | None,
    means_b: MechanismMeans | None,
) -> str:
    if means_a is None or means_b is None:
        return "unpaired"
    if means_b.requests_started > means_a.requests_started:
        return "more_codegen_requests"
    if (
        means_a.mean_prompt_chars_per_request is not None
        and means_b.mean_prompt_chars_per_request is not None
        and means_b.mean_prompt_chars_per_request > means_a.mean_prompt_chars_per_request
    ):
        return "larger_prompt_per_request"
    if (
        means_a.input_tokens_per_request is not None
        and means_b.input_tokens_per_request is not None
        and means_b.input_tokens_per_request > means_a.input_tokens_per_request
    ):
        return "tokenization_or_stochastic_effect"
    return "no_codegen_input_increase"


def _summary_by_agent(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_agent = summary.get("by_agent", {})
    return by_agent if isinstance(by_agent, dict) else {}


def _mean_summary_agent(summaries: list[dict[str, Any]], agent: str, key: str) -> float:
    return mean(
        float(_summary_by_agent(summary).get(agent, {}).get(key, 0) or 0)
        for summary in summaries
    )


def _mean_optional(values: Any) -> float | None:
    numeric_values = [float(value) for value in values if value is not None]
    return mean(numeric_values) if numeric_values else None


def _case_comparison(
    case_id: str,
    means_a: TokenMeans | None,
    means_b: TokenMeans | None,
) -> CaseTokenComparison:
    paired = means_a is not None and means_b is not None
    if not paired:
        return CaseTokenComparison(
            case_id=case_id,
            a=means_a,
            b=means_b,
            paired=False,
            delta_total=None,
            delta_total_pct=None,
            delta_input=None,
            delta_output=None,
            delta_by_agent={},
        )

    assert means_a is not None and means_b is not None
    common_agents = sorted(set(means_a.by_agent) & set(means_b.by_agent))
    delta_by_agent = {
        agent: AgentDelta(
            input=means_b.by_agent[agent].input - means_a.by_agent[agent].input,
            output=means_b.by_agent[agent].output - means_a.by_agent[agent].output,
            total=means_b.by_agent[agent].total - means_a.by_agent[agent].total,
        )
        for agent in common_agents
    }
    return CaseTokenComparison(
        case_id=case_id,
        a=means_a,
        b=means_b,
        paired=True,
        delta_total=means_b.total - means_a.total,
        delta_total_pct=_delta_pct(means_a.total, means_b.total),
        delta_input=means_b.input - means_a.input,
        delta_output=means_b.output - means_a.output,
        delta_by_agent=delta_by_agent,
    )


def _unpaired_case(
    case_id: str,
    means_a: TokenMeans | None,
    means_b: TokenMeans | None,
    raw_a_present: bool,
    raw_b_present: bool,
) -> UnpairedCase | None:
    if means_a is not None and means_b is None:
        reason = "case_absent_in_other_arm" if not raw_b_present else "no_valid_runs_in_other_arm"
        return UnpairedCase(case_id=case_id, present_in="a_only", reason=reason)
    if means_b is not None and means_a is None:
        reason = "case_absent_in_other_arm" if not raw_a_present else "no_valid_runs_in_other_arm"
        return UnpairedCase(case_id=case_id, present_in="b_only", reason=reason)
    return None


def _agent_aggregates(paired_cases: list[CaseTokenComparison]) -> list[AgentAggregate]:
    agents = sorted(
        {
            agent
            for case in paired_cases
            for agent in case.delta_by_agent
        }
    )
    aggregates = []
    for agent in agents:
        case_pairs = [
            (case.a.by_agent[agent], case.b.by_agent[agent])
            for case in paired_cases
            if case.a is not None
            and case.b is not None
            and agent in case.a.by_agent
            and agent in case.b.by_agent
        ]
        if not case_pairs:
            continue
        a_total = mean(pair[0].total for pair in case_pairs)
        b_total = mean(pair[1].total for pair in case_pairs)
        a_input = mean(pair[0].input for pair in case_pairs)
        b_input = mean(pair[1].input for pair in case_pairs)
        aggregates.append(
            AgentAggregate(
                agent=agent,
                n_cases=len(case_pairs),
                a_mean_total=a_total,
                b_mean_total=b_total,
                delta_total_pct=_delta_pct(a_total, b_total),
                a_mean_input=a_input,
                b_mean_input=b_input,
                delta_input_pct=_delta_pct(a_input, b_input),
            )
        )
    return aggregates


def _io_split(paired_cases: list[CaseTokenComparison]) -> IOSplit:
    means_a = [case.a for case in paired_cases if case.a is not None]
    means_b = [case.b for case in paired_cases if case.b is not None]
    a_input = _mean_field(means_a, "input")
    b_input = _mean_field(means_b, "input")
    a_output = _mean_field(means_a, "output")
    b_output = _mean_field(means_b, "output")
    a_total = _mean_field(means_a, "total")
    b_total = _mean_field(means_b, "total")
    return IOSplit(
        a_input=a_input,
        b_input=b_input,
        input_delta_pct=_delta_pct(a_input, b_input),
        a_output=a_output,
        b_output=b_output,
        output_delta_pct=_delta_pct(a_output, b_output),
        a_total=a_total,
        b_total=b_total,
        total_delta_pct=_delta_pct(a_total, b_total),
    )


def _mean_field(values: list[TokenMeans], field: str) -> float:
    if not values:
        return 0.0
    return mean(float(getattr(value, field)) for value in values)


def _direction_summary(paired_cases: list[CaseTokenComparison]) -> PairedDirectionSummary:
    deltas = [
        case.delta_total_pct
        for case in paired_cases
        if case.delta_total_pct is not None
    ]
    return PairedDirectionSummary(
        n_paired_cases=len(paired_cases),
        n_delta_pct_cases=len(deltas),
        cases_b_higher=sum(1 for case in paired_cases if (case.delta_total or 0) > 0),
        cases_b_lower=sum(1 for case in paired_cases if (case.delta_total or 0) < 0),
        cases_equal=sum(1 for case in paired_cases if (case.delta_total or 0) == 0),
        mean_delta_pct=mean(deltas) if deltas else None,
        median_delta_pct=median(deltas) if deltas else None,
        min_delta_pct=min(deltas) if deltas else None,
        max_delta_pct=max(deltas) if deltas else None,
        directional_only=True,
    )


def _caveats(
    paired_case_ids: list[str],
    validity_a: ArmValidity,
    validity_b: ArmValidity,
    unpaired_cases: list[UnpairedCase],
) -> list[str]:
    caveats = []
    if len(paired_case_ids) < 10:
        caveats.append(
            f"Only {len(paired_case_ids)} paired cases; directional only, no significance claimed."
        )
    if len(paired_case_ids) != 0:
        caveats.append("Delta percentage summaries skip paired cases where arm A has a zero-token baseline.")
        caveats.append("Per-agent input percentages can be high-variance at small baselines; use aggregate input split as the stable view.")
    if validity_a.config_token_total is None or validity_b.config_token_total is None:
        caveats.append("Config-level cross-check unavailable for at least one arm.")
    for validity in (validity_a, validity_b):
        if validity.cross_check_match is False:
            caveats.append(
                f"{validity.name} config-level token cross-check mismatch: diff={validity.cross_check_diff}."
            )
    infra_a = validity_a.excluded.get("infra_error", 0)
    infra_b = validity_b.excluded.get("infra_error", 0)
    if infra_a != infra_b:
        caveats.append(
            f"Asymmetric infra exclusion: {validity_a.name}={infra_a}, {validity_b.name}={infra_b}."
        )
    if unpaired_cases:
        caveats.append(f"{len(unpaired_cases)} cases are unpaired and excluded from paired deltas.")
    return caveats


def _config_total(config_token_summary: dict[str, Any] | None) -> int | None:
    if not config_token_summary:
        return None
    total = config_token_summary.get("total")
    return int(total) if total is not None else None


def _delta_pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b - a) / a * 100


def _agent_input(means_value: TokenMeans | None, agent: str) -> float | None:
    if means_value is None or agent not in means_value.by_agent:
        return None
    return means_value.by_agent[agent].input


def _means_total(means_value: TokenMeans | None) -> float | None:
    return means_value.total if means_value is not None else None


def _mechanism_requests(means_value: MechanismMeans | None) -> float | None:
    return means_value.requests_started if means_value is not None else None


def _mechanism_prompt_per_request(means_value: MechanismMeans | None) -> float | None:
    return means_value.mean_prompt_chars_per_request if means_value is not None else None


def _mechanism_input_per_request(means_value: MechanismMeans | None) -> float | None:
    return means_value.input_tokens_per_request if means_value is not None else None


def _fmt_float(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "-"
    if signed:
        return f"{value:+,.1f}"
    return f"{value:,.1f}"


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "-"
    if signed:
        return f"{value:+.1f}%"
    return f"{value:.1f}%"


def _fmt_int(value: int | None) -> str:
    return "-" if value is None else f"{value:,}"


def _format_excluded(excluded: dict[str, int]) -> str:
    non_zero = [f"{reason}={count}" for reason, count in excluded.items() if count]
    return ", ".join(non_zero) if non_zero else "0"


def _format_cross_check(validity: ArmValidity) -> str:
    if validity.cross_check_match is None:
        return "-"
    if validity.cross_check_match:
        return "match"
    return f"mismatch ({validity.cross_check_diff:+,})"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
