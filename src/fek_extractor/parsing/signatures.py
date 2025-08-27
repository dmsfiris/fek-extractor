from __future__ import annotations

import re
import unicodedata

from ..utils.logging import get_logger
from .normalize import normalize_text

log = get_logger(__name__)

# Strict uppercase name line (Greek/Latin, spaces, hyphen, apostrophes)
_UPPER_NAME_RE = re.compile(r"(?u)^[A-ZΑ-ΩΆΈΉΊΌΎΏΪΫ][A-ZΑ-ΩΆΈΉΊΌΎΏΪΫ’'´\.\-\s]{2,}$")

# Inline uppercase name tail on the same line (capture group 1)
_INLINE_NAME_RE = re.compile(r"(?u)([A-ZΑ-ΩΆΈΉΊΌΎΏΪΫ][A-ZΑ-ΩΆΈΉΊΌΎΏΪΫ’'´\.\-\s]*?)\s*$")

# Footer/appendix stop hints (folded/lowercased comparison)
_STOP_HINTS = (
    "θεωρήθηκε",
    "τέθηκε η μεγάλη σφραγίδα",
    "τεύχος",
    "εφημερίδα της κυβερνήσεως",
)


def _fold(s: str) -> str:
    """Lowercase + remove Greek diacritics for accent-insensitive matching."""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s


def _is_upper_name_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    return bool(_UPPER_NAME_RE.match(s))


def _looks_like_stop(line: str) -> bool:
    low = _fold(line)
    return any(h in low for h in _STOP_HINTS)


def find_signatories(lines: list[str], tail_scan: int = 200) -> list[dict[str, str]]:
    """
    Scan the last `tail_scan` lines for signature blocks.

    Patterns handled:
      - 'Η|H Πρόεδρος της Δημοκρατίας'  -> next uppercase name line
      - 'Ο ... Υπουργός' (incl. 'επί της ... Υπουργός') -> next uppercase name line
      - 'Οι Υπουργοί' -> subsequent uppercase name lines (skip ministry lines)
      - Inline uppercase name at end of title line
    """
    n = len(lines)
    start = max(0, n - tail_scan)
    window = [normalize_text(ln) for ln in lines[start:]]
    folded = [_fold(ln) for ln in window]

    out: list[dict[str, str]] = []
    i = 0
    while i < len(window):
        line = window[i].strip()
        fline = folded[i].strip()
        if not line:
            i += 1
            continue

        if _looks_like_stop(line):
            log.debug("Stopping at footer hint: %r", line)
            break

        # Case A: plural "Οι Υπουργοί"
        if fline == "οι υπουργοι":
            j = i + 1
            while j < len(window):
                cand = window[j].strip()
                if not cand:
                    j += 1
                    continue
                if _looks_like_stop(cand):
                    break
                if _is_upper_name_line(cand):
                    out.append({"title": "Υπουργός", "name": cand})
                j += 1
            i = j
            continue

        # Case B: Πρόεδρος της Δημοκρατίας (Η or Latin H)
        if fline.startswith(("η προεδρος της δημοκρατιας", "h προεδρος της δημοκρατιας")):
            title = line
            pres_name: str | None = None
            # inline first
            mi = _INLINE_NAME_RE.search(line)
            if mi and _is_upper_name_line(mi.group(1)):
                pres_name = mi.group(1).strip()
            # otherwise next uppercase line
            if not pres_name:
                for j in range(i + 1, min(i + 8, len(window))):
                    cand = window[j].strip()
                    if _is_upper_name_line(cand):
                        pres_name = cand
                        break
                    if _looks_like_stop(cand):
                        break
            if pres_name:
                out.append({"title": title, "name": pres_name})
                i += 2
                continue

        # Case C: any single-person minister title line (Ο/Η/H ... Υπουργός)
        if fline.startswith(("ο ", "η ", "h ")) and " υπουργος" in fline:
            title = line
            minister_name: str | None = None
            # inline name at end of line?
            mi = _INLINE_NAME_RE.search(line)
            if mi and _is_upper_name_line(mi.group(1)):
                minister_name = mi.group(1).strip()
            # otherwise next uppercase line
            if not minister_name:
                for j in range(i + 1, min(i + 8, len(window))):
                    cand = window[j].strip()
                    if _is_upper_name_line(cand):
                        minister_name = cand
                        break
                    if _looks_like_stop(cand):
                        break
            if minister_name:
                out.append({"title": title, "name": minister_name})
                i += 2
                continue

        i += 1

    log.debug("Signatories found: %d (scanned last %d lines)", len(out), tail_scan)
    return out
