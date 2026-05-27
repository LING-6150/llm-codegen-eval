"""EvalCase: standard test case definition for LLM code generation."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class CodeType(str, Enum):
    HTML = "html"
    MULTI_FILE = "multi_file"
    VUE_PROJECT = "vue_project"

class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EDGE = "edge"

class ElementCheck(BaseModel):
    """A single check on the generated code."""
    type: str  # "tag_exists" | "tag_count" | "attr_exists" | "text_contains" | "regex_match"
    selector: Optional[str] = None
    attribute: Optional[str] = None
    pattern: Optional[str] = None
    expected: int | str | None = None
    description: str

class EvalCase(BaseModel):
    """A standard evaluation case."""
    case_id: str
    prompt: str
    code_type: CodeType
    difficulty: Difficulty = Difficulty.MEDIUM

    required_checks: list[ElementCheck] = Field(default_factory=list)
    optional_checks: list[ElementCheck] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)

    notes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
