from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pypdf import PdfReader


_PYPDF_LOGGER_NAMES = ("pypdf", "pypdf._reader")


@contextmanager
def _suppress_recoverable_pypdf_logs() -> Iterator[None]:
    loggers = [logging.getLogger(name) for name in _PYPDF_LOGGER_NAMES]
    previous_levels = [logger.level for logger in loggers]
    try:
        for logger in loggers:
            logger.setLevel(logging.ERROR)
        yield
    finally:
        for logger, level in zip(loggers, previous_levels):
            logger.setLevel(level)


def extract_pdf_text(path: Path, *, page_limit: int = 6, char_limit: int = 30000) -> str:
    with _suppress_recoverable_pypdf_logs():
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for index, page in enumerate(reader.pages[:page_limit], start=1):
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(f"[page {index}]\n{text.strip()}")
    joined = "\n\n".join(chunks)
    return joined[:char_limit]
