from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Dict, List, Any, Optional

from .normalize import normalize_text


def parse_text(text: str, patterns: Optional[List[str]] = None) -> Dict[str, Any]:
    """Parse raw text to structured info using regex rules and counters.

    Extend this with FEK-specific field extraction.
    """
    text_norm = normalize_text(text)

    words = re.findall(r"\w+", text_norm, flags=re.UNICODE)
    char_counter = Counter(text_norm)
    word_counter = Counter(w.lower() for w in words)

    matches: Dict[str, List[str]] = {}
    if patterns:
        for pat in patterns:
            try:
                rx = re.compile(pat, flags=re.UNICODE | re.IGNORECASE | re.MULTILINE)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern {pat!r}: {e}") from e
            matches[pat] = [m.group(0) for m in rx.finditer(text_norm)]

    line_lengths = [len(line) for line in text_norm.splitlines() if line.strip()]
    med_len = median(line_lengths) if line_lengths else 0

    return {
        "length": len(text_norm),
        "num_lines": len([ln for ln in text_norm.splitlines() if ln.strip()]),
        "median_line_length": med_len,
        "char_counts": dict(char_counter.most_common(20)),
        "word_counts_top": dict(word_counter.most_common(20)),
        "matches": matches,
    }
