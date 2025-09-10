# src/fek_extractor/core.py
from __future__ import annotations

import re
from collections import OrderedDict
from os import PathLike
from pathlib import Path
from typing import Any

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTPage

from .io.pdf import _iter_lines, count_pages, extract_pdf_text, infer_decision_number
from .metrics import text_metrics
from .parsing.articles import build_articles_map
from .parsing.articles_norm import article_sort_key
from .parsing.headers import parse_fek_header
from .parsing.normalize import dehyphenate_text, normalize_text

# Convenience alias for public API
Pathish = str | Path | PathLike[str]


def extract_pdf_info(
    pdf_path: Pathish,
    include_metrics: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Return FEK header fields and parsed articles from a PDF.
    If include_metrics=True, merge basic text metrics at the top level.
    """
    # Normalize once to a real Path (use a new local so mypy knows its type)
    p: Path = Path(pdf_path)

    debug: bool = bool(kwargs.get("debug", False))

    # NEW: accept an optional page from kwargs (from CLI)
    raw_dp = kwargs.get("debug_pages")
    if isinstance(raw_dp, str):
        try:
            raw_dp = int(raw_dp)
        except ValueError:
            raw_dp = None
    debug_pages: int | None = raw_dp if isinstance(raw_dp, int) and raw_dp > 0 else None

    # 1) Extract full text (headers/footers filtered)
    full_text: str = extract_pdf_text(p, debug=debug, debug_pages=debug_pages)

    # Precompute normalized text once (used by decision + metrics)
    text_norm: str = normalize_text(full_text)

    # Use de-hyphenated body only for article parsing
    body_src: str = dehyphenate_text(full_text)

    # 2) Build a light "masthead" blob from first couple of pages
    masthead_lines: list[str] = []
    try:
        for i, layout in enumerate(extract_pages(str(p))):
            if not isinstance(layout, LTPage):
                continue
            if i >= 2:
                break
            h: float = float(getattr(layout, "height", 0.0))
            for _x0, y0, _x1, y1, txt in _iter_lines(layout):
                if not txt:
                    continue
                in_band = (y1 >= 0.80 * h) or (y0 <= 0.18 * h)
                has_token = re.search(r"(?:^|\s)(ΤΕΥΧΟΣ|ΦΕΚ)\b|Αρ\.\s*Φύλλου", txt, re.IGNORECASE)
                if in_band or has_token:
                    masthead_lines.append(txt)
    except Exception:  # noqa: BLE001
        # If masthead probing fails for any reason, proceed without it.
        pass

    header_source: str = ("\n".join(masthead_lines) + "\n" + full_text).strip()

    # 3) FEK header fields
    header: dict[str, str] = parse_fek_header(header_source)

    # Decision number (from normalized text)
    decision = infer_decision_number(text_norm)
    if decision:
        header["decision_number"] = decision

    # 4) Articles (ordered)
    articles_dict: dict[str, Any] = build_articles_map(body_src)
    articles_ordered: OrderedDict[str, Any] = OrderedDict(
        sorted(articles_dict.items(), key=lambda kv: article_sort_key(kv[0]))
    )

    # 5) Compose record
    record: dict[str, Any] = {
        "filename": p.name,
        "path": str(p),
        "pages": count_pages(p),
        **header,
        "articles": articles_ordered,
    }

    # 6) Optional metrics
    if include_metrics:
        record.update(text_metrics(full_text, text_norm=text_norm))

    return record


def extract(
    input_path: Pathish,
    include_metrics: bool = False,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Υψηλού επιπέδου API: δέχεται path σε PDF ή φάκελο με PDF και επιστρέφει λίστα από records.
    Δέχεται και περνάει ό,τι επιπλέον kwargs (π.χ. dehyphenate) στο extract_pdf_info().
    """
    p = Path(input_path)
    results: list[dict[str, Any]] = []

    if p.is_file() and p.suffix.lower() == ".pdf":
        results.append(extract_pdf_info(p, include_metrics=include_metrics, **kwargs))
        return results

    if p.is_dir():
        for pdf in sorted(p.glob("**/*.pdf")):
            try:
                rec = extract_pdf_info(pdf, include_metrics=include_metrics, **kwargs)
                results.append(rec)
            except Exception as e:
                results.append(
                    {
                        "path": str(pdf),
                        "filename": pdf.name,
                        "error": str(e),
                    }
                )
        return results

    raise FileNotFoundError(f"Not a PDF or directory: {input_path}")
