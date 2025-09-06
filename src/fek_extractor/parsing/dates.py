from __future__ import annotations

import re
from datetime import date

__all__ = ["parse_date_to_iso"]


# Απλή αποστιγμάτωση/αποτονισμός για αντιστοίχιση μηνών
def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    repl = {
        "ά": "α",
        "έ": "ε",
        "ή": "η",
        "ί": "ι",
        "ό": "ο",
        "ύ": "υ",
        "ώ": "ω",
        "ϊ": "ι",
        "ΐ": "ι",
        "ϋ": "υ",
        "ΰ": "υ",
        "ς": "σ",
        ".": "",
    }
    out = []
    for ch in s:
        out.append(repl.get(ch, ch))
    return "".join(out)


# Χαρτογράφηση ονομάτων μηνών (συντομογραφίες & γενικές)
_MONTHS = {
    # Ιανουάριος
    "ιαν": 1,
    "ιανουαριος": 1,
    "ιανουαριου": 1,
    # Φεβρουάριος
    "φεβ": 2,
    "φεβρουαριος": 2,
    "φεβρουαριου": 2,
    # Μάρτιος
    "μαρ": 3,
    "μαρτιος": 3,
    "μαρτιου": 3,
    # Απρίλιος
    "απρ": 4,
    "απριλιος": 4,
    "απριλιου": 4,
    # Μάιος
    "μαι": 5,
    "μαιου": 5,
    # Ιούνιος
    "ιουν": 6,
    "ιουνιος": 6,
    "ιουνιου": 6,
    # Ιούλιος
    "ιουλ": 7,
    "ιουλιος": 7,
    "ιουλιου": 7,
    # Αύγουστος
    "αυγ": 8,
    "αυγουστος": 8,
    "αυγουστου": 8,
    # Σεπτέμβριος
    "σεπ": 9,
    "σεπτεμβριος": 9,
    "σεπτεμβριου": 9,
    "σεπτ": 9,
    # Οκτώβριος
    "οκτ": 10,
    "οκτωβριος": 10,
    "οκτωβριου": 10,
    # Νοέμβριος
    "νοε": 11,
    "νοεμβριος": 11,
    "νοεμβριου": 11,
    # Δεκέμβριος
    "δεκ": 12,
    "δεκεμβριος": 12,
    "δεκεμβριου": 12,
}


# 1) 03.01.2018 / 3/1/2018 / 3-1-2018
DMY_SEP = re.compile(r"\b(?P<d>\d{1,2})\s*[-./]\s*(?P<m>\d{1,2})\s*[-./]\s*(?P<y>\d{4})\b")

# 2) 3 Ιανουαρίου 2018 (με/χωρίς τόνους/τελείες)
DMY_GREEK = re.compile(
    r"\b(?P<d>\d{1,2})\s+(?P<mon>[A-Za-zΑ-ΩΆ-Ώα-ωάέήίόύώϊΐϋΰ\.]+)\s+(?P<y>\d{4})\b", re.UNICODE
)


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date_to_iso(s: str) -> str | None:
    """
    Δέχεται ελληνική ημερομηνία σε κείμενο και γυρίζει 'YYYY-MM-DD' ή None.
    Υποστηρίζει:
      - 3.1.2018 / 3/1/2018 / 3-1-2018
      - 3 Ιανουαρίου 2018 (με/χωρίς τόνους/συντμήσεις)
    """
    if not s:
        return None
    text = s.strip()

    # 1) 03.01.2018 κ.λπ.
    m = DMY_SEP.search(text)
    if m:
        d = int(m.group("d"))
        mo = int(m.group("m"))
        y = int(m.group("y"))
        dt = _safe_date(y, mo, d)
        return dt.isoformat() if dt else None

    # 2) 3 Ιανουαρίου 2018
    m = DMY_GREEK.search(text)
    if m:
        d = int(m.group("d"))
        y = int(m.group("y"))
        mon_raw = _normalize(m.group("mon"))
        mo_opt = _MONTHS.get(mon_raw)  # Optional[int]
        if mo_opt is None:
            # δοκίμασε να κόψεις τελικά 'ου', 'ος' κ.λπ. για ασυνήθιστες παραλλαγές
            for trim in (
                "ου",
                "ος",
            ):
                if mon_raw.endswith(trim):
                    mo_opt = _MONTHS.get(mon_raw[: -len(trim)])
                    if mo_opt is not None:
                        break
        if mo_opt is not None:
            dt = _safe_date(y, mo_opt, d)
            return dt.isoformat() if dt else None

    return None
