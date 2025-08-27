from __future__ import annotations

from pathlib import Path
from typing import Any

from .io.pdf import extract_text_whole, iter_lines_from_pdf
from .parsing.rules import parse_text


def extract_pdf_info(pdf_path: Path, patterns: list[str] | None = None) -> dict[str, Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    raw_text = extract_text_whole(pdf_path)
    parsed = parse_text(raw_text, patterns=patterns)
    lines = iter_lines_from_pdf(pdf_path)
    record: dict[str, Any] = {
        "path": str(pdf_path),
        "filename": pdf_path.name,
        "pages": raw_text.count("\f") + 1 if raw_text else 0,
        **parsed,
        "first_5_lines": lines[:5],
    }
    return record
