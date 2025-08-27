# src/fek_extractor/parsing/subject.py
from __future__ import annotations

import re
import unicodedata

from .normalize import normalize_text
from .titles import is_article_head_line


def _fold(s: str) -> str:
    """Lowercase + strip diacritics (accent-insensitive matching)."""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# Require a word boundary after "θεμα" so we DON'T match "θεματα"
_SUBJECT_PREFIX_RE = re.compile(r"^\s*θεμα\b\s*[:\-–—]?\s*", re.IGNORECASE)
_STOP_HINTS = ("κυρίως κείμενο", "κυριως κειμενο")


def _is_blank(line: str) -> bool:
    return not line.strip()


def _starts_subject(line: str) -> bool:
    # Only use the boundary-aware regex (drop naive startswith to avoid "θεματα")
    return _SUBJECT_PREFIX_RE.match(_fold(line)) is not None


def _stop_subject(line: str) -> bool:
    f = _fold(line)
    return any(h in f for h in _STOP_HINTS) or is_article_head_line(line)


def _strip_subject_prefix(line: str) -> str:
    # Fast reject
    if not _SUBJECT_PREFIX_RE.match(_fold(line)):
        return line.strip()
    # Slice on original with a boundary after ΜΑ
    m2 = re.match(r"^\s*Θ(?:Ε|Έ|ε|έ)ΜΑ\b\s*[:\-–—]?\s*", line, re.IGNORECASE)
    return line[m2.end() :].strip() if m2 else line.strip()


def extract_subject(
    lines: list[str],
    search_window: int = 60,
    max_lines: int = 6,
) -> str | None:
    """
    Find a ΘΕΜΑ subject near the top; collect continuation lines.
    Join with a space by default; if the next line does not start with a conjunction
    like 'και'/'ή', insert a comma before it to avoid awkward bigrams in some cases.
    """
    window = lines[: max(0, min(search_window, len(lines)))]
    parts: list[str] = []
    started = False
    consumed = 0

    for _idx, raw in enumerate(window):
        line = normalize_text(raw)

        if not started:
            if _starts_subject(line):
                started = True
                consumed = 1
                body = _strip_subject_prefix(line)
                if body:
                    parts.append(body)
            continue

        if _is_blank(line) or _stop_subject(line):
            break

        seg = line.strip()
        fseg = _fold(seg)
        # If continuation starts with conjunction, don't add a comma
        if fseg.startswith("και ") or fseg.startswith("η ") or fseg.startswith("ή "):
            joiner = " "
        else:
            joiner = ", "
        parts.append(joiner + seg)

        consumed += 1
        if consumed >= max_lines:
            break

    if not started:
        return None

    subject = "".join(parts).strip()
    subject = re.sub(r"\s+", " ", subject)
    subject = re.sub(r"[\s,;:—–\-]+$", "", subject)
    subject = re.sub(r"\s+([:—–\-])\s*", r" \1 ", subject).strip()
    subject = re.sub(r"\s{2,}", " ", subject)

    return subject or None
