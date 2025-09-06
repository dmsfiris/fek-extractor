from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


@dataclass(frozen=True)
class Context:
    part_letter: str | None = None
    part_title: str | None = None
    title_letter: str | None = None
    title_title: str | None = None
    chapter_letter: str | None = None
    chapter_title: str | None = None
    # NEW: between ΚΕΦΑΛΑΙΟ and Άρθρο
    section_letter: str | None = None  # ΤΜΗΜΑ
    section_title: str | None = None  # ΤΜΗΜΑ


@dataclass
class Article:
    number: str
    title: str
    html: str
    context: Context


class ExtractionRecord(TypedDict, total=False):
    # Identity / header
    filename: str
    extracted_at: str
    fek_series: str
    fek_number: str
    fek_date: str
    fek_date_iso: str
    decision_number: str
    subject: str

    # IO / structure
    pages: int
    articles: dict[str, dict[str, Any]]

    # Optional metrics (only present if include_metrics=True)
    length: int
    num_lines: int
    median_line_length: int
    char_counts: dict[str, int]
    word_counts_top: dict[str, int]
    chars: int
    words: int
    pattern_matches: dict[str, list[str]]
    matches: dict[str, list[str]]
