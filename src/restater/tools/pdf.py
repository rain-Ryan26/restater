from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def extract_pdf_text(path: Path, *, page_limit: int = 6, char_limit: int = 30000) -> str:
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for index, page in enumerate(reader.pages[:page_limit], start=1):
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(f"[page {index}]\n{text.strip()}")
    joined = "\n\n".join(chunks)
    return joined[:char_limit]

