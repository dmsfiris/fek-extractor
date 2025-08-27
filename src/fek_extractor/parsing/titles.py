# src/fek_extractor/parsing/titles.py
from __future__ import annotations

import re

from .normalize import normalize_text

# Matches: "Άρθρο 1", "ΑΡΘΡΟ 12", "  άρθρο 3", etc.
# Accept either Ά or Α at the start; rest is case-insensitive.
_ARTICLE_HEAD_RE = re.compile(
    r"^\s*[ΆΑ]ρθρο\s+(?P<num>\d{1,3})\b",
    flags=re.IGNORECASE | re.MULTILINE,
)

# Allowed separators after the article number (colon, em/en dash, hyphen, dot).
# Hyphen placed last to avoid character-range issues.
_SEP_RE = re.compile(r"\s*[\:\u2014\u2013\.\-]\s*")


def is_article_head_line(line: str) -> bool:
    """True if the line starts with an article heading."""
    return _ARTICLE_HEAD_RE.match(normalize_text(line)) is not None


def extract_article_number(line: str) -> int | None:
    """Return the article number if the line is an article heading."""
    m = _ARTICLE_HEAD_RE.match(normalize_text(line))
    if not m:
        return None
    try:
        return int(m.group("num"))
    except ValueError:
        return None


def split_inline_title_and_body(line: str) -> tuple[str, str]:
    """
    If an article heading has an inline title, split it.
    Returns (title, body). If no inline title, title is the heading itself and body is "".
    """
    norm = normalize_text(line)
    m = _ARTICLE_HEAD_RE.match(norm)
    if not m:
        return (line.strip(), "")

    after = norm[m.end() :]
    # Strip an optional separator and treat the rest of the line as title
    after = _SEP_RE.sub("", after, count=1)
    inline_title = after.strip()

    if inline_title:
        # Title is just the text after the heading and optional separator
        return (inline_title, "")
    # No inline title; return the heading as the title
    return (m.group(0).strip(), "")
