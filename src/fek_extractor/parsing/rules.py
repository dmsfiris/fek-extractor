from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Any

from ..constants import DECISION_NO_RX, FEK_HEADER_RX, SUBJECT_LINE_RX
from ..utils.dates import parse_date_to_iso
from .normalize import normalize_text


def extract_fields(text_raw: str, text_norm: str) -> dict[str, Any]:
    """Domain-specific extraction (use normalized for headers; raw for line-anchored SUBJECT)."""
    fields: dict[str, Any] = {}

    # FEK header & decision number work well on normalized text
    m = FEK_HEADER_RX.search(text_norm)
    if m:
        date_raw = m.group("date")
        fields["fek_series"] = m.group("series")
        fields["fek_number"] = m.group("number")
        fields["fek_date"] = date_raw
        if iso := parse_date_to_iso(date_raw):
            fields["fek_date_iso"] = iso

    m = DECISION_NO_RX.search(text_norm)
    if m:
        fields["decision_number"] = m.group("decision")

    # SUBJECT: capture exactly one line from the RAW text (line-start anchor matters)
    m = SUBJECT_LINE_RX.search(text_raw)
    if m:
        # normalize just the captured line (collapse internal spaces)
        subject = normalize_text(m.group("subject"))
        fields["subject"] = subject

    return fields


def parse_text(text: str, patterns: list[str] | None = None) -> dict[str, Any]:
    """Generic metrics + optional regex matches + FEK-specific fields."""
    text_norm = normalize_text(text)

    # — metrics —
    words = re.findall(r"\w+", text_norm, flags=re.UNICODE)
    char_counter = Counter(text_norm)
    word_counter = Counter(w.lower() for w in words)

    # — optional regex matches (from CLI) —
    matches: dict[str, list[str]] = {}
    if patterns:
        for pat in patterns:
            rx = re.compile(pat, flags=re.UNICODE | re.IGNORECASE | re.MULTILINE)
            matches[pat] = [m.group(0) for m in rx.finditer(text_norm)]

    # — quick document profile —
    line_lengths = [len(line) for line in text_norm.splitlines() if line.strip()]
    med_len = median(line_lengths) if line_lengths else 0

    # — domain fields —
    fields = extract_fields(text, text_norm)

    return {
        "length": len(text_norm),
        "num_lines": len([ln for ln in text_norm.splitlines() if ln.strip()]),
        "median_line_length": med_len,
        "char_counts": dict(char_counter.most_common(20)),
        "word_counts_top": dict(word_counter.most_common(20)),
        "matches": matches,
        **fields,
    }
