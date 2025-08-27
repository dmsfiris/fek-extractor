# src/fek_extractor/parsing/authority.py
from __future__ import annotations

import re
import unicodedata


def _fold(s: str) -> str:
    """Lowercase + strip diacritics (accent-insensitive matching)."""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# Heuristics for authority lines near the top of a FEK/act.
# We match on a folded (accent-insensitive) view, but return the original (trimmed) line.
_PATTERNS: list[re.Pattern[str]] = [
    # Υπουργείο Οικονομικών
    re.compile(r"^\s*(?:το\s+)?υπουργειο\s+.+$"),
    # Βουλή των Ελλήνων
    re.compile(r"^\s*βουλη\s+των\s+ελληνων\s*$"),
    # Προεδρία/Πρόεδρος της Δημοκρατίας
    re.compile(r"^\s*προεδρ(ια|ος)\s+της\s+δημοκρατιας\s*$"),
    # Ανεξάρτητη Αρχή ...
    re.compile(r"^\s*ανεξαρτητ[ηο]\s+αρχ[ηη]\s+.+$"),
    # ΑΠΟΦΑΣΗ (sometimes header)
    re.compile(r"^\s*αποφαση\s*$"),
    # Γενική Γραμματεία ...
    re.compile(r"^\s*γενικ[οη]\s+γραμματε(ια|ας)\s+.+$"),
    # Φορέας: ...
    re.compile(r"^\s*φορεας\s*:\s*.+$"),
]


def find_issuing_authorities(
    lines: list[str],
    head_scan: int = 120,
    max_hits: int = 3,
) -> list[str]:
    """
    Scan the first `head_scan` lines and return up to `max_hits` authority lines (trimmed),
    preserving the original order/lettercase.
    """
    window = lines[: max(0, min(head_scan, len(lines)))]
    out: list[str] = []
    for raw in window:
        s = raw.strip()
        if not s:
            continue
        f = _fold(s)
        if any(rx.match(f) for rx in _PATTERNS):
            # Avoid near-duplicates
            if s not in out:
                out.append(s)
            if len(out) >= max_hits:
                break
    return out
