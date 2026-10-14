from dataclasses import dataclass, field
from ..core.case import EvalCase
from ..core.result import ExecutionSmokeResult, BehaviorCheck, BehaviorResult

class BehaviorCase(EvalCase):
    behavior_id: str
    contract_version: str = "1"


@dataclass
class BrowserOutcome:
    smoke: ExecutionSmokeResult
    behavior: BehaviorResult
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    blocked_requests: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)
    evidence_errors: list[str] = field(default_factory=list)
