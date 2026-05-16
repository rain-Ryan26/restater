from __future__ import annotations

import fnmatch
from pathlib import Path


TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".java",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".html",
    ".css",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
    ".cmd",
    ".properties",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".v",
    ".vh",
    ".sv",
    ".svh",
    ".xdc",
    ".tcl",
    ".sdc",
    ".asm",
    ".s",
    ".hex",
}

EXCLUDED_DIRS = {
    ".git",
    ".restater",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "target",
    "build",
    "dist",
}


def find_files(root: Path, *, limit: int = 300) -> list[Path]:
    results: list[Path] = []
    for path in root.rglob("*"):
        if len(results) >= limit:
            break
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            results.append(path)
    return results


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def read_text_preview(path: Path, *, limit: int = 20000) -> str:
    if not is_text_file(path):
        return ""
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    return text[:limit]


def write_text_no_bom(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def search_text(root: Path, terms: list[str], *, patterns: list[str] | None = None, limit: int = 30) -> list[str]:
    if not terms:
        return []
    lowered_terms = [term.lower() for term in terms if term]
    ranked_matches: list[tuple[int, str, str]] = []
    for path in find_files(root, limit=1000):
        rel = str(path.relative_to(root))
        if patterns and not any(fnmatch.fnmatch(rel, pattern) for pattern in patterns):
            continue
        if not is_text_file(path):
            continue
        try:
            text = read_text_preview(path, limit=50000)
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        matched_terms = [term for term in lowered_terms if term in lowered]
        if matched_terms:
            ranked_matches.append((match_score(rel, matched_terms), rel, f"{rel}: contains {', '.join(matched_terms[:5])}"))
    ranked_matches.sort(key=lambda item: (-item[0], item[1]))
    return [message for _, _, message in ranked_matches[:limit]]


def match_score(relative_path: str, matched_terms: list[str]) -> int:
    lowered_path = relative_path.lower().replace("\\", "/")
    score = len(matched_terms) * 10
    for marker in ["test_report", "stage", "status", "state", "report", "result", "coverage", "regression"]:
        if marker in lowered_path:
            score += 8
    for marker in ["test", "run", "check", "verify", "verification"]:
        if marker in lowered_path:
            score += 4
    return score
