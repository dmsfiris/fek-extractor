# src/fek_extractor/parsing/headers.py
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import cast

__all__ = [
    "find_fek_header_line",
    "parse_fek_header",
    "parse_fek_header_fallback",
]

# Map spelled-out series to canonical letter
_SERIES_WORD_TO_LETTER: dict[str, str] = {
    "ΠΡΩΤΟ": "Α",
    "ΔΕΥΤΕΡΟ": "Β",
    "ΤΡΙΤΟ": "Γ",
    "ΤΕΤΑΡΤΟ": "Δ",
    "ΠΡΩΤΟΝ": "Α",
    "ΔΕΥΤΕΡΟΝ": "Β",
    "ΤΡΙΤΟΝ": "Γ",
    "ΤΕΤΑΡΤΟΝ": "Δ",
}
_LATIN_TO_GREEK_SERIES: dict[str, str] = {"A": "Α", "B": "Β", "G": "Γ", "D": "Δ"}

_STRIP_CHARS = "".join(["'", "’", "´", "`", "′", "ʹ"])
_SERIES_TOKEN = r"[A-ZΑ-ΩΆΈΉΊΌΎΏ][A-ZΑ-ΩΆΈΉΊΌΎΏ’']*"

# Strict compact header: ΦΕΚ/ΤΕΥΧΟΣ <series> ... <issue> ... <date>
_COMPACT_HEADER_RE = re.compile(
    rf"""
    (?:^|[\s,;])                 # start or separator
    (?:ΦΕΚ|ΤΕΥΧΟΣ)\s+            # FEK or TEYXOS
    (?P<series>{_SERIES_TOKEN})  # series token
    .*?                          # up to number
    (?P<number>\d{{1,5}})        # issue number
    [^\d]*                       # separators
    (?P<date>                    # date (allow newline before year)
        (?<!\d)\d{{1,2}}[./\-]\d{{1,2}}[./\-]\s*\d{{2,4}}(?!\d)
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

# Numeric date finder with guards (not inside other numbers)
_NUMERIC_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})[./\-](\d{1,2})[./\-]\s*(\d{2,4})(?!\d)",
    flags=re.DOTALL,
)


def _import_date_parser() -> Callable[[str], str | None]:
    try:
        from .dates import parse_date_to_iso

        return cast(Callable[[str], str | None], parse_date_to_iso)
    except Exception:
        # fallback: πάντα γύρνα None, για να μην σκάει αν λείπει ο parser
        def _fallback(_: str) -> str | None:
            return None

        return _fallback


def _to_series_letter(token: str) -> str:
    if not token:
        return ""
    # καθάρισε τυχόν τελικά σημεία στίξης μαζί με αποστρόφους
    t = token.strip().upper()
    t = t.translate(str.maketrans("", "", _STRIP_CHARS))
    t = re.sub(r"[.,;·:·]+$", "", t)  # κόψε τυχόν τελικά σημεία στίξης

    if t in {"Α", "Β", "Γ", "Δ"}:
        return t
    if t in _LATIN_TO_GREEK_SERIES:
        return _LATIN_TO_GREEK_SERIES[t]
    if t in _SERIES_WORD_TO_LETTER:
        return _SERIES_WORD_TO_LETTER[t]
    return ""


def _extract_date_tokens(s: str) -> tuple[str | None, str | None]:
    """
    Return (fek_date, fek_date_iso).
    Prefer matches with 4-digit year; tie-break by rightmost.
    """
    best: tuple[int, int, int, int, int] | None = None
    for m in _NUMERIC_DATE_RE.finditer(s):
        d, mth, y = m.groups()
        try:
            dd = int(d)
            mm = int(mth)
        except ValueError:
            continue
        if not (1 <= dd <= 31 and 1 <= mm <= 12):
            continue

        year_raw = y
        yyyy = (
            year_raw
            if len(year_raw) == 4
            else ("20" + year_raw if int(year_raw) < 50 else "19" + year_raw)
        )
        try:
            y_int = int(yyyy)
        except ValueError:
            continue
        if not (1800 <= y_int <= 2100):
            continue

        score = (1 if len(year_raw) == 4 else 0, m.start())
        if best is None or score > (best[0], best[1]):
            best = (score[0], score[1], dd, mm, y_int)

    if best is not None:
        _, _, dd, mm, yyyy = best
        return f"{dd:02d}.{mm:02d}.{yyyy:04d}", f"{yyyy:04d}-{mm:02d}-{dd:02d}"

    parse_date_to_iso = _import_date_parser()
    iso2 = parse_date_to_iso(s)
    if iso2:
        try:
            yyyy_s, mm_s, dd_s = iso2.split("-")
            dotted2 = f"{int(dd_s):02d}.{int(mm_s):02d}.{int(yyyy_s):04d}"
            return dotted2, iso2
        except Exception:
            return None, iso2

    return None, None


def _parse_compact_line(s: str) -> dict[str, str]:
    """
    Parse only a strict 'ΦΕΚ/ΤΕΥΧΟΣ <series> <issue>/<date>' snippet.
    Avoid grabbing unrelated numbers (e.g., page counters).
    """
    out: dict[str, str] = {}
    m = _COMPACT_HEADER_RE.search(s)
    if not m:
        return out

    ser = _to_series_letter(m.group("series"))
    if ser:
        out["fek_series"] = ser

    out["fek_number"] = m.group("number")

    dotted, iso = _extract_date_tokens(m.group("date"))
    if dotted:
        out["fek_date"] = dotted
    if iso:
        out["fek_date_iso"] = iso

    return out


def _parse_three_line_masthead(s: str) -> dict[str, str]:
    """
    Parse the common masthead trio:
      ΤΕΥΧΟΣ <word> ; Αρ. Φύλλου <n> ; <date>
    Works even if on separate lines within 's'.
    """
    out: dict[str, str] = {}

    m1 = re.search(rf"ΤΕΥΧΟΣ\s+({_SERIES_TOKEN})", s, flags=re.IGNORECASE | re.UNICODE)
    if m1:
        ser = _to_series_letter(m1.group(1))
        if ser:
            out["fek_series"] = ser

    m2 = re.search(r"Αρ\.\s*Φύλλου?\s+(\d+)\b", s, flags=re.IGNORECASE)
    if m2:
        out["fek_number"] = m2.group(1)

    dotted, iso = _extract_date_tokens(s)
    if dotted:
        out["fek_date"] = dotted
    if iso:
        out["fek_date_iso"] = iso

    return out


def find_fek_header_line(text: str | Sequence[str]) -> str | None:
    """
    Return a representative compact header line if spotted, otherwise the
    first 'ΤΕΥΧΟΣ ...' line. Accepts a string or a sequence of lines.
    """
    joined: str = text if isinstance(text, str) else "\n".join(text)
    m = _COMPACT_HEADER_RE.search(joined)
    if m:
        return m.group(0).strip()

    for ln in joined.splitlines():
        if re.search(r"^\s*ΤΕΥΧΟΣ\b", ln, flags=re.IGNORECASE):
            return ln.strip()
    return None


def parse_fek_header(text: str) -> dict[str, str]:
    """
    Extract FEK header fields:
      - 'fek_series'   (Α/Β/Γ/Δ)
      - 'fek_number'   (Αρ. Φύλλου)
      - 'fek_date'     (dd.mm.yyyy)
      - 'fek_date_iso' (YYYY-MM-DD)
    Strategy:
      1) Try strict compact line.
      2) If incomplete, parse masthead trio in the whole text.
      3) Merge, preferring compact values where present.
    """
    compact = _parse_compact_line(text)
    if all(k in compact for k in ("fek_series", "fek_number", "fek_date_iso")):
        return compact

    mast = _parse_three_line_masthead(text)
    out: dict[str, str] = dict(mast)
    out.update(compact)
    return {k: v for k, v in out.items() if v}


def parse_fek_header_fallback(text: str) -> dict[str, str]:
    """Explicit masthead fallback."""
    return _parse_three_line_masthead(text)
