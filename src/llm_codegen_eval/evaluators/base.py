"""Base class for all evaluators."""

from abc import ABC, abstractmethod
from ..core.case import EvalCase
from ..core.result import EvalResult

class BaseEvaluator(ABC):

    @abstractmethod
    async def evaluate(self, code: str, case: EvalCase) -> EvalResult:
        ...
