from __future__ import annotations

import re

from .normalize import normalize_text

# Matches: "Άρθρο 1", "ΑΡΘΡΟ 12", "  άρθρο 3", etc.
# We accept either Ά or Α at the start and use IGNORECASE for the rest.
_ARTICLE_HEAD_RE = re.compile(
    r"^\s*[ΆΑ]ρθρο\s+(?P<num>\d{1,3})\b",
    flags=re.IGNORECASE | re.MULTILINE,
)

# Allowed separators after the article number (colon, em dash, en dash, hyphen, dot)
# Hyphen is escaped (or placed last) to avoid creating a character range.
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
    # Keep the original for output, but match using a normalized view
    norm = normalize_text(line)
    m = _ARTICLE_HEAD_RE.match(norm)
    if not m:
        return (line.strip(), "")

    after = norm[m.end() :]
    # strip an optional separator and treat the rest of the line as title
    after = _SEP_RE.sub("", after, count=1)
    inline_title = after.strip()

    if inline_title:
        # Title is "Άρθρο N — <title>"
        return (inline_title, "")
    # No inline title; return the heading as title
    return (m.group(0).strip(), "")
