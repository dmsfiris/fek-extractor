# src/fek_extractor/metrics.py
from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Any

from .parsing.normalize import normalize_text


def text_metrics(text: str, text_norm: str | None = None) -> dict[str, Any]:
    """
    Basic text metrics. Accept a pre-normalized string to save work if you have it.
    """
    lines = text.splitlines()
    non_empty = [len(ln) for ln in lines if ln]
    out: dict[str, Any] = {
        "length": len(text),
        "num_lines": len(lines),
        "median_line_length": int(median(non_empty)) if non_empty else 0,
        "char_counts": dict(Counter(text)),
    }

    # word counts (use normalized text if provided)
    tn = text_norm if text_norm is not None else normalize_text(text)
    tokens = re.findall(r"[A-Za-zΑ-Ωά-ώΆ-Ώ]+", tn)
    counts = Counter(t.lower() for t in tokens if t)
    out["word_counts_top"] = dict(counts.most_common(20))
    out["words"] = int(sum(counts.values()))
    return out
