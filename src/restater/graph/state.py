from __future__ import annotations

from typing import TypedDict

from restater.models import (
    CompletionEstimate,
    ContextItem,
    EvidenceItem,
    FindingItem,
    InspectionProgress,
    InspectionStep,
    RequirementItem,
    RequirementSource,
    RequirementSourceReview,
    RunError,
    ShellResult,
    ValidationAttempt,
)


class ProjectCheckState(TypedDict, total=False):
    run_id: str
    project_path: str
    user_note: str
    output_dir: str
    context_index: list[ContextItem]
    requirement_sources: list[RequirementSource]
    requirement_source_reviews: list[RequirementSourceReview]
    requirements: list[RequirementItem]
    plan: list[InspectionStep]
    inspection_iteration: int
    inspection_complete: bool
    inspection_decision: str
    inspection_progress: InspectionProgress
    evidence: list[EvidenceItem]
    findings: list[FindingItem]
    completion_estimate: CompletionEstimate | None
    report_path: str | None
    errors: list[RunError]
    shell_results: list[ShellResult]
    validation_attempts: list[ValidationAttempt]
    reasoning_log: list[str]
