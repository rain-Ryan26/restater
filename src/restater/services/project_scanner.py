from __future__ import annotations

from pathlib import Path

from restater.config import RestaterConfig
from restater.models import ContextItem, RequirementSource
from restater.tools.filesystem import find_files, is_text_file, read_text_preview
from restater.tools.pdf import extract_pdf_text


REQUIREMENT_KEYWORDS = [
    "requirement",
    "requirements",
    "assignment",
    "rubric",
    "spec",
    "任务",
    "要求",
    "评分",
    "提交",
    "说明",
]

REQUIREMENT_DIR_MARKERS = {
    "requirement",
    "requirements",
    "rubric",
    "assignment",
    "spec",
    "specs",
}

REQUIREMENT_FILE_NAMES = {
    "agent.md",
    "agents.md",
    "readme.md",
}


class ProjectScanner:
    def __init__(self, config: RestaterConfig) -> None:
        self.config = config

    def scan(self, project_path: Path) -> tuple[list[ContextItem], list[RequirementSource]]:
        context: list[ContextItem] = []
        sources: list[RequirementSource] = []
        for path in find_files(project_path, limit=self.config.context_file_limit):
            rel = str(path.relative_to(project_path))
            kind, confidence = classify_path(rel, path)
            summary = self._summarize(path)
            context.append(ContextItem(path=rel, kind=kind, summary=summary, confidence=confidence))
            if kind == "requirement":
                source_type = "pdf" if path.suffix.lower() == ".pdf" else "text"
                sources.append(
                    RequirementSource(path=rel, source_type=source_type, summary=summary, confidence=confidence)
                )
        return context, sources

    def _summarize(self, path: Path) -> str:
        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                text = extract_pdf_text(path, page_limit=self.config.pdf_page_limit, char_limit=2000)
                return compact(text) or "PDF text could not be extracted in the first pass."
            if is_text_file(path):
                return compact(read_text_preview(path, limit=2000))
        except Exception as exc:
            return f"Preview failed: {exc}"
        return ""


def classify_path(relative_path: str, path: Path) -> tuple[str, float]:
    lowered = relative_path.lower()
    name = path.name.lower()
    suffix = path.suffix.lower()

    if is_requirement_candidate(relative_path, name, suffix):
        return "requirement", 0.8
    if "test" in lowered or "spec" in name:
        return "test", 0.75
    if suffix in {".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".c", ".cpp", ".h", ".hpp", ".go", ".rs"}:
        return "code", 0.7
    if suffix in {".md", ".txt", ".docx"}:
        if "state" in lowered or "stage" in lowered or "status" in lowered or "状态" in lowered:
            return "state", 0.75
        return "doc", 0.55
    if suffix in {".pdf", ".zip", ".ppt", ".pptx", ".xlsx", ".csv"}:
        return "artifact", 0.5
    return "unknown", 0.2


def is_requirement_candidate(relative_path: str, name: str, suffix: str) -> bool:
    if suffix not in {".pdf", ".md", ".txt", ".docx"}:
        return False

    lowered = relative_path.lower()
    parts = {part for part in lowered.replace("\\", "/").split("/") if part}
    stem = Path(name).stem.lower()

    if parts.intersection(REQUIREMENT_DIR_MARKERS):
        return True
    if name in REQUIREMENT_FILE_NAMES:
        return True
    return any(keyword in stem for keyword in REQUIREMENT_KEYWORDS)


def compact(text: str) -> str:
    return " ".join(text.split())[:1000]
