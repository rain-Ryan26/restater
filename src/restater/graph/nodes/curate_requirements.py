from __future__ import annotations

import re

from restater.graph.state import ProjectCheckState
from restater.models import RequirementItem, RequirementSourceReview, RunError


SOURCE_LEVEL_PATTERNS = [
    "review requirement source",
    "model extraction did not produce structured items",
    "inspect this text requirement source",
    "inspect this pdf requirement source",
]


def make_curate_requirements_node(progress=None):
    def curate_requirements(state: ProjectCheckState) -> dict:
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("curate_requirements: filter source-level and non-authoritative candidate requirements.")
        errors = list(state.get("errors", []))
        candidates = normalize_requirements(state.get("requirements", []))
        reviews = normalize_reviews(state.get("requirement_source_reviews", []))
        review_by_path = {normalize_path(review.path): review for review in reviews}

        curated: list[RequirementItem] = []
        dropped = 0
        seen_keys: set[str] = set()
        for requirement in candidates:
            if is_source_level_requirement(requirement):
                dropped += 1
                continue
            review = review_by_path.get(normalize_path(requirement.source_path))
            if review is not None and review.role != "authoritative_requirement":
                dropped += 1
                continue
            key = requirement_key(requirement)
            if key in seen_keys:
                dropped += 1
                continue
            seen_keys.add(key)
            curated.append(requirement)

        if candidates and not curated:
            errors.append(
                RunError(
                    stage="curate_requirements",
                    message="No reliable requirements remained after filtering candidate requirements.",
                    detail="Source-level fallback items and non-authoritative README/index/status documents were excluded.",
                )
            )

        if progress:
            progress(
                "curate_requirements",
                "trace",
                f"candidate_requirements={len(candidates)}, curated={len(curated)}, dropped={dropped}",
            )

        return {"requirements": curated, "errors": errors, "reasoning_log": reasoning_log}

    return curate_requirements


def normalize_requirements(items: list[RequirementItem | dict]) -> list[RequirementItem]:
    return [item if isinstance(item, RequirementItem) else RequirementItem(**item) for item in items]


def normalize_reviews(items: list[RequirementSourceReview | dict]) -> list[RequirementSourceReview]:
    return [item if isinstance(item, RequirementSourceReview) else RequirementSourceReview(**item) for item in items]


def is_source_level_requirement(requirement: RequirementItem) -> bool:
    text = f"{requirement.title} {requirement.description}".lower()
    return any(pattern in text for pattern in SOURCE_LEVEL_PATTERNS)


def requirement_key(requirement: RequirementItem) -> str:
    text = f"{requirement.title} {requirement.description}".lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lower()
