# src/fek_extractor/parsing/rules.py
from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Any

from ..constants import DECISION_NO_RX, FEK_HEADER_RX, SUBJECT_LINE_RX
from ..utils.dates import parse_date_to_iso
from .normalize import normalize_text
from .subject import extract_subject


def _fold(s: str) -> str:
    """Lowercase + strip diacritics for accent/tonos-insensitive matching."""
    import unicodedata

    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def extract_fields(text_raw: str, text_norm: str) -> dict[str, Any]:
    """
    Extract FEK-specific fields from the given text.

    Heuristics:
    - Use the *normalized* text for FEK header.
    - Decision number: prefer law header "ΝΟΜΟΣ ΥΠ’ ΑΡΙΘ. <num>"; otherwise
      use line-anchored Αριθ. <num> if it truly contains a number.
    - SUBJECT: prefer robust multiline extractor on RAW lines; fall back to a
      single-line regex if needed (and strip the 'ΘΕΜΑ' prefix).
    """
    fields: dict[str, Any] = {}

    # FEK header (series, number, date [+ iso]) from normalized text
    m = FEK_HEADER_RX.search(text_norm)
    if m:
        date_raw = m.group("date")
        fields["fek_series"] = m.group("series")
        fields["fek_number"] = m.group("number")
        fields["fek_date"] = date_raw
        if iso := parse_date_to_iso(date_raw):
            fields["fek_date_iso"] = iso

    # Decision number (Law number)
    folded = _fold(text_norm)

    # 1) Strong signal: "ΝΟΜΟΣ ΥΠ’ ΑΡΙΘ. <num>" (accept any punctuation between ΥΠ and ΑΡΙΘ)
    m_law = re.search(r"\bνομος\s+υπ\W*αριθ\W*(\d{1,6})\b", folded)
    if m_law:
        fields["decision_number"] = m_law.group(1)
    else:
        # 2) Line-anchored Αριθ. <...> in RAW text, but only keep numeric
        m_raw = DECISION_NO_RX.search(text_raw)
        if m_raw:
            gd = m_raw.groupdict()
            tail = gd.get("decision", "").strip()
            m_num = re.search(r"\b(\d{1,6})\b", tail)
            if m_num:
                fields["decision_number"] = m_num.group(1)
        # 3) Fallback anywhere in normalized text
        if "decision_number" not in fields:
            m_any = re.search(r"(?i)\bαριθ[\.μ]*\s*(?P<num>\d{1,6})\b", text_norm)
            if m_any:
                fields["decision_number"] = m_any.group("num")

    # SUBJECT (ΘΕΜΑ): prefer robust multiline extractor on RAW lines
    subj = extract_subject(text_raw.splitlines())
    if subj:
        fields["subject"] = subj
    else:
        # Fallback: tolerant single-line capture on RAW text
        m = SUBJECT_LINE_RX.search(text_raw)
        if m:
            gd = m.groupdict()
            # tolerate either 'body' (current) or legacy 'subject' group names
            body = gd.get("body") or gd.get("subject") or m.group(0)
            subject = normalize_text(body)
            # strip any lingering ΘΕΜΑ prefix (accent/case tolerant)
            subject = re.sub(
                r"^\s*Θ(?:Ε|Έ|ε|έ)ΜΑ\s*[:\-–—]?\s*",
                "",
                subject,
                flags=re.IGNORECASE,
            ).strip()
            fields["subject"] = subject

    return fields


def _apply_user_patterns(
    text_norm: str,
    patterns: list[str] | None,
) -> dict[str, list[str]]:
    """
    Apply user-supplied regex patterns (if any) to the normalized text and
    return a mapping pattern -> list of matched strings (may be empty).
    Invalid patterns are ignored.
    """
    results: dict[str, list[str]] = {}
    if not patterns:
        return results

    flags = re.UNICODE | re.IGNORECASE | re.MULTILINE
    for pat in patterns:
        try:
            rx = re.compile(pat, flags)
        except re.error:
            # Skip invalid regex; caller already validated on the CLI.
            continue
        results[pat] = [m.group(0) for m in rx.finditer(text_norm)]
    return results


def _word_counts_top(text_norm: str, limit: int = 20) -> dict[str, int]:
    """Simple word frequency table from normalized text."""
    tokens = re.findall(r"[A-Za-zΑ-Ωά-ώΆ-Ώ]+", text_norm)
    counts = Counter(t.lower() for t in tokens if t)
    return dict(counts.most_common(limit))


def parse_text(text: str, patterns: list[str] | None = None) -> dict[str, Any]:
    """
    High-level parser used by the core pipeline.

    Returns a dictionary with:
      - FEK fields (series/number/date[/iso], decision_number)
      - subject (if detected)
      - basic counts (chars, words, length, num_lines, median_line_length, char_counts,
        word_counts_top)
      - matches/pattern_matches (if patterns provided)
    """
    text_norm = normalize_text(text)

    out = extract_fields(text, text_norm)

    # Basic metrics
    out["chars"] = len(text)
    out["words"] = len(text_norm.split())

    lines = text.splitlines()
    out["length"] = len(text)  # alias for chars to satisfy tests
    out["num_lines"] = len(lines)
    non_empty = [len(ln) for ln in lines if ln]
    out["median_line_length"] = int(median(non_empty)) if non_empty else 0
    out["char_counts"] = dict(Counter(text))
    out["word_counts_top"] = _word_counts_top(text_norm, limit=20)

    # Optional user patterns over normalized text
    if patterns:
        pm = _apply_user_patterns(text_norm, patterns)
        out["pattern_matches"] = pm  # keep for API stability
        out["matches"] = pm  # alias for tests/compat

    return out
