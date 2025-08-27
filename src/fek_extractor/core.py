# src/fek_extractor/core.py
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import SCHEMA_VERSION
from .io.pdf import extract_text_whole, iter_lines_from_pdf
from .parsing.articles import (
    Article,
    ArticleIndex,
    build_articles,
    build_toc,
    find_articles_in_text,
)
from .parsing.authority import find_issuing_authorities
from .parsing.headers import find_fek_header_line, parse_fek_header
from .parsing.normalize import dehyphenate_text
from .parsing.rules import parse_text
from .parsing.signatures import find_signatories
from .parsing.subject import extract_subject
from .utils.dates import parse_date_to_iso

# ----------------------------
# Sorting & de-dup helpers
# ----------------------------


def _article_idx_sort_key(a: ArticleIndex) -> tuple[int, int]:
    """Sort lightweight article index by number, then by line position."""
    return (a["number"], a["line_index"])


def _article_full_sort_key(a: Article) -> tuple[int, int]:
    """Sort full article entries by number, then by start_line."""
    return (a["number"], a["start_line"])


# Titles that look like inline references rather than true article titles.
# Examples to ignore as titles:
#   "του ν. 1234/2020", "του πδ. 50/2001", "... /2019", etc.
_REF_TITLE_RE = re.compile(r"(?i)\bτου\s+(?:ν\.?|πδ\.?|π\.δ\.)\b|/\d{4}\b")

_ARTICLE_HEADING_ONLY_RE = re.compile(r"(?i)^\s*[ΆΑ]ρθρο\s+\d+\s*$")


def _score_article_idx(a: ArticleIndex) -> int:
    """
    Score an ArticleIndex entry for de-duplication.
    Higher is better:
      +2 if the title is a meaningful phrase (not just "Άρθρο N")
      -2 if the title looks like an inline reference to another law/PD
    """
    title = (a.get("title") or "").strip()
    score = 0
    if title and not _ARTICLE_HEADING_ONLY_RE.match(title):
        score += 2
    if _REF_TITLE_RE.search(title):
        score -= 2
    return score


def _dedupe_articles_index(items: list[ArticleIndex]) -> list[ArticleIndex]:
    """
    Keep a single entry per article number.
    Preference order:
      1) "Meaningful" title over bare "Άρθρο N"
      2) Non-reference titles over reference-like ones (πδ./ν. patterns)
      3) Lower line_index as a tie-breaker (stable, often TOC title)
    """
    best: dict[int, ArticleIndex] = {}
    best_score: dict[int, int] = {}

    for a in items:
        num = a["number"]
        score = _score_article_idx(a)

        if num not in best:
            best[num] = a
            best_score[num] = score
            continue

        current = best[num]
        cur_score = best_score[num]

        if score > cur_score:
            best[num] = a
            best_score[num] = score
        elif score == cur_score:
            # tie-breaker: earlier line wins
            if a["line_index"] < current["line_index"]:
                best[num] = a
                best_score[num] = score

    return sorted(best.values(), key=_article_idx_sort_key)


# ----------------------------
# Main extractor
# ----------------------------


def extract_pdf_info(
    pdf_path: Path,
    patterns: list[str] | None = None,
    dehyphenate: bool = True,
) -> dict[str, Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    # Raw text (full-document)
    raw_text = extract_text_whole(pdf_path)

    # Count pages from the original text (form-feeds intact)
    pages = raw_text.count("\f") + 1 if raw_text else 0

    # Optional dehyphenation
    if dehyphenate:
        raw_text = dehyphenate_text(raw_text)

    # Parse generic metrics + FEK-specific fields from text
    parsed = parse_text(raw_text, patterns=patterns)

    # Per-line view for headers/signatures and first_5_lines preview
    lines = iter_lines_from_pdf(pdf_path)

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "path": str(pdf_path),
        "filename": pdf_path.name,
        "pages": pages,
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

    # Subject (ΘΕΜΑ): if missing from text parsing, try line-based extractor
    if not record.get("subject"):
        subj = extract_subject(lines)
        if subj:
            record["subject"] = subj

    # Issuing authority (top-of-doc heuristics)
    authorities = find_issuing_authorities(lines)
    if authorities:
        record["issuing_authorities"] = authorities
        record["issuing_authority"] = authorities[0]

    # Article index (numbers + titles + line indexes) — de-duplicated & sorted
    articles_idx: list[ArticleIndex] = find_articles_in_text(raw_text)
    articles_idx = _dedupe_articles_index(articles_idx)
    record["articles"] = articles_idx
    record["articles_count"] = len(articles_idx)

    # Full articles (with bodies) — sorted; TOC from sorted list
    articles_full: list[Article] = build_articles(raw_text)
    articles_full_sorted = sorted(articles_full, key=_article_full_sort_key)
    record["articles_full"] = articles_full_sorted
    record["toc"] = build_toc(articles_full_sorted)

    # Signatories (scan near the end of the document)
    record["signatories"] = find_signatories(lines, tail_scan=200)

    return record
