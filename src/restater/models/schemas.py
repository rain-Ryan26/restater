from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContextItem(BaseModel):
    path: str
    kind: Literal["requirement", "code", "test", "doc", "state", "artifact", "unknown"]
    summary: str = ""
    confidence: float = 0.0


class RequirementSource(BaseModel):
    path: str
    source_type: Literal["pdf", "text", "doc"]
    summary: str = ""
    confidence: float = 0.0


class RequirementSourceReview(BaseModel):
    path: str
    role: Literal[
        "authoritative_requirement",
        "routing_hint",
        "implementation_doc",
        "status_or_test_evidence",
        "low_confidence",
    ]
    reason: str
    confidence: float = 0.0


class RequirementItem(BaseModel):
    id: str
    title: str
    description: str
    source_path: str
    category: Literal["function", "document", "test", "submission", "quality", "unknown"] = "unknown"
    verifiable_in_repo: bool = True
    confidence: float = 0.0


class InspectionStep(BaseModel):
    id: str
    target_requirement_ids: list[str] = Field(default_factory=list)
    action: str
    expected_evidence: str = ""
    tool_hint: Literal["filesystem", "shell", "pdf", "model"] = "filesystem"
    file_patterns: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    id: str
    requirement_id: str | None = None
    source: Literal["file", "pdf", "shell", "model"]
    content_summary: str
    raw_ref: str | None = None


class FindingItem(BaseModel):
    requirement_id: str
    status: Literal["done", "partial", "missing", "unknown"]
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class CompletionEstimate(BaseModel):
    percent: float
    basis: str
    done: int = 0
    partial: int = 0
    missing: int = 0
    unknown: int = 0
    excluded: int = 0


class RunError(BaseModel):
    stage: str
    message: str
    detail: str = ""


class ShellResult(BaseModel):
    command: str
    cwd: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
