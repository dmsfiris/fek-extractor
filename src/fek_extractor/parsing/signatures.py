from __future__ import annotations

import re

from .normalize import normalize_text

# Greek titles we often see in signature blocks
# Match at line start; accept male/female and common roles.
_SIGN_TITLE_RE = re.compile(
    r"(?im)^\s*(Ο|Η)\s+("
    r"αναπληρωτ[ήςί]\s+υπουργός|"
    r"αναπλ\.?\s*υπουργός|"
    r"υφυπουργός|"
    r"υπουργός|"
    r"πρόεδρος|"
    r"διοικητής|"
    r"γενικ[όςή]\s+γραμματέας|"
    r"περιφερειάρχης"
    r")\b"
)

# A simple "looks like a name" line (tolerant: Greek or Latin, with spaces & punctuation)
_NAME_CANDIDATE_RE = re.compile(
    r"(?u)^[A-Za-zΑ-ΩΆΈΉΊΌΎΏΪΫ][A-Za-zΑ-Ωα-ωΆΈΉΊΌΎΏΪΫϊϋΐΰ\.\-’'´\s]{2,}$"
)

# Lines to skip as they’re not names even if they look title-ish
_SKIP_HINTS = (
    "με εντολή",  # "By order of"
    "αθήνα",  # date/place lines
    "ημερομηνία",
    "η υπηρ",  # e.g., "Η Υπηρεσία ..."
    "τηλ.",
    "φαξ",
)


def _looks_like_name(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    s_low = s.lower()
    if any(h in s_low for h in _SKIP_HINTS):
        return False
    return bool(_NAME_CANDIDATE_RE.match(s))


def find_signatories(lines: list[str], tail_scan: int = 120) -> list[dict[str, str]]:
    """
    Scan the last `tail_scan` lines for signature blocks like:
      'Ο Υπουργός ...'  <newline>  'ΓΙΩΡΓΟΣ ΠΑΠΑΔΟΠΟΥΛΟΣ'
    Returns list of {title, name}.
    """
    n = len(lines)
    start = max(0, n - tail_scan)
    window = [normalize_text(ln) for ln in lines[start:]]

    out: list[dict[str, str]] = []
    i = 0
    while i < len(window):
        line = window[i]
        m = _SIGN_TITLE_RE.match(line)
        if not m:
            i += 1
            continue

        title = m.group(0).strip()  # keep the Greek case as-is
        # Look ahead a few lines for a name
        name: str | None = None
        for j in range(i + 1, min(i + 4, len(window))):
            cand = window[j].strip()
            if _looks_like_name(cand):
                name = cand
                break

        if name:
            out.append({"title": title, "name": name})

        # Advance; avoid re-finding the same block
        i = i + 2
    return out
