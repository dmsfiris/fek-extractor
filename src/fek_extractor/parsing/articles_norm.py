# src/fek_extractor/parsing/articles_norm.py
from __future__ import annotations

import re

__all__ = ["article_sort_key"]

_ARTICLE_HDR_RE = re.compile(
    r"^\s*Άρθρο\s+(\d+[A-Za-zΑ-Ωα-ω]?)\s*(?:[:\-–—]\s*(.+))?\s*$",
    flags=re.IGNORECASE,
)

_ART_KEY_RE = re.compile(r"^\s*(\d+)\s*([A-Za-zΑ-Ωα-ω]*)\s*$")
_LATIN_TO_GREEK = str.maketrans({"A": "Α", "B": "Β", "G": "Γ", "D": "Δ"})


def article_sort_key(key: str) -> tuple[int, str]:
    m = _ART_KEY_RE.match(key or "")
    if not m:
        return (10_000_000, key or "")
    n, suf = m.groups()
    suf_norm = (suf or "").upper().translate(_LATIN_TO_GREEK)
    return (int(n), suf_norm)


def _split_article_heading(title: str) -> tuple[str | None, str | None]:
    m = _ARTICLE_HDR_RE.match(title or "")
    if not m:
        return None, None
    num = m.group(1)
    subtitle = (m.group(2) or "").strip() or None
    return num, subtitle


def _format_article_title(num: str, subtitle: str | None) -> str:
    return f"Άρθρο {num}" + (f": {subtitle}" if subtitle else "")
