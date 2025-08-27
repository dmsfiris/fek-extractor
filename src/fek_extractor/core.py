# src/fek_extractor/core.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from .io.pdf import extract_text_whole, iter_lines_from_pdf
from .parsing.articles import build_articles, build_toc, find_articles_in_text
from .parsing.headers import find_fek_header_line, parse_fek_header
from .parsing.normalize import dehyphenate_text
from .parsing.rules import parse_text
from .parsing.signatures import find_signatories
from .utils.dates import parse_date_to_iso


def extract_pdf_info(
    pdf_path: Path,
    patterns: list[str] | None = None,
    dehyphenate: bool = True,
) -> dict[str, Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    # Raw text (full-document)
    raw_text = extract_text_whole(pdf_path)
    if dehyphenate:
        raw_text = dehyphenate_text(raw_text)

    # Parse generic metrics + FEK-specific fields from text
    parsed = parse_text(raw_text, patterns=patterns)

    # Per-line view (layout-aware) for headers/signatures and first_5_lines preview
    lines = iter_lines_from_pdf(pdf_path)

    record: dict[str, Any] = {
        "path": str(pdf_path),
        "filename": pdf_path.name,
        "pages": raw_text.count("\f") + 1 if raw_text else 0,
        **parsed,
        "first_5_lines": lines[:5],
    }

    # Enrich FEK fields from header lines (top-of-page area)
    header_line = find_fek_header_line(lines)
    if header_line:
        hdr = parse_fek_header(header_line)
        for k in ("fek_series", "fek_number", "fek_date"):
            if hdr.get(k) and not record.get(k):
                record[k] = hdr[k]
        if (
            record.get("fek_date")
            and not record.get("fek_date_iso")
            and (iso := parse_date_to_iso(record["fek_date"]))
        ):
            record["fek_date_iso"] = iso

    # Article index (numbers + titles + line indexes)
    articles_idx = find_articles_in_text(raw_text)
    record["articles"] = articles_idx
    record["articles_count"] = len(articles_idx)

    # Full articles (with bodies) and a simple TOC
    articles_full = build_articles(raw_text)
    record["articles_full"] = articles_full
    record["toc"] = build_toc(articles_full)

    # Signatories (scan near the end of the document)
    record["signatories"] = find_signatories(lines, tail_scan=200)

    return record
