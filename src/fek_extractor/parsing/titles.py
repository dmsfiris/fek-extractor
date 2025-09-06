# src/fek_extractor/parsing/titles.py
from __future__ import annotations

import re

__all__ = [
    "is_article_head_line",
    "extract_article_number",
    "split_inline_title_and_body",
]

# We expect callers (e.g., articles.py) to pass *normalized* lines.
# Pattern matches: "Άρθρο 1", "ΑΡΘΡΟ 12", "  άρθρο 3", etc.
_ARTICLE_HEAD_RE = re.compile(
    r"^\s*[ΆΑ]ρθρο\s+(?P<num>\d{1,3})\b",
    flags=re.IGNORECASE,
)

# Allowed single leading separator after the number (colon, em/en dash, hyphen, dot,
# Greek ano teleia). Use ^ so we only trim the very beginning of the remainder, and
# count=1.
_SEP_RE = re.compile(r"^\s*[:\u2014\u2013\.\-\u0387\u00B7]\s*")


def is_article_head_line(line: str) -> bool:
    """
    True if the *normalized* line starts with an article heading.
    Caller is responsible for normalization.
    """
    return _ARTICLE_HEAD_RE.match(line) is not None


def extract_article_number(line: str) -> int | None:
    """
    Return the article number (int) if the *normalized* line is a heading, else None.
    """
    m = _ARTICLE_HEAD_RE.match(line)
    if not m:
        return None
    try:
        return int(m.group("num"))
    except ValueError:
        return None


def split_inline_title_and_body(line: str) -> tuple[str, str]:
    """
    If an article heading line has an inline title, split it.
    Assumes *normalized* input.
    Returns (title, body). If no inline title is present, returns (heading_text, "").
    - title is JUST the inline portion (e.g., "Πεδίο εφαρμογής"), not "Άρθρο 1: …".
    - body is always "" here; multi-line body is handled by the slicer in articles.py.
    """
    m = _ARTICLE_HEAD_RE.match(line)
    if not m:
        return (line.strip(), "")

    # Text after "Άρθρο <num>"
    after = line[m.end() :]

    # Strip one leading separator (e.g., ":", "—", "–", "-", ".", "·", "·") and trim
    after = _SEP_RE.sub("", after, count=1)
    inline_title = after.strip()

    if inline_title:
        return (inline_title, "")

    # No inline title; expose the matched heading as a user-visible fallback
    return (m.group(0).strip(), "")
