from typing import Literal

from pydantic import BaseModel, Field


InvariantCategory = Literal["architecture", "technical", "stack", "business"]


class ProjectInvariant(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    category: InvariantCategory
    title: str = Field(..., min_length=1, max_length=200)
    rule: str = Field(..., min_length=1, max_length=2000)
    rationale: str | None = Field(default=None, max_length=2000)


class ProjectInvariants(BaseModel):
    version: str = Field(default="1.0", min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=2000)
    invariants: list[ProjectInvariant] = Field(default_factory=list)


class InvariantViolation(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=200)
    reason: str = Field(..., min_length=1, max_length=1000)


class InvariantCheckResult(BaseModel):
    allowed: bool = True
    relevant_invariants: list[str] = Field(default_factory=list)
    violations: list[InvariantViolation] = Field(default_factory=list)
    reasoning_summary: str = Field(default="")
