# src/fek_extractor/io/pdf.py
"""
PDF text extraction with robust 2-column detection, safe single-column tail
(after columns), ET Gazette header/footer filtering, Greek de-hyphenation,
article heading clustering, and smart tail trimming.

Key behaviors:
- Two-column split via k-means + vertical occupancy valley.
- Tail zone = anything physically *below* both columns' bottoms (strict).
- Demotions that send lines from columns to the single-column tail:
    • Article-switch by WIDTH change: for each new "Άρθρο N" in a column,
      if one of the next 3 lines crosses the split (becomes full-width), we
      demote from that head downward to the tail (column ended).
    • "Unfinished sentence → new article" (guarded): same demotion, but only
      when we've already entered the articles body (avoids TOC false positives).
    • Strict article-gap demotion within a column (e.g., 60 → 62 while 61 is
      not on this page and not seen before) — demote from 62 downward.
- Trim end-of-document from the first proclamation/signature/date/seal line
  that appears *after* the last article block on the page OR from an ANNEX
  heading (ΠΑΡΑΡΤΗΜΑ ...). When such a terminal anchor is hit on a page,
  all subsequent pages are dropped.
- Single debug page or set of pages via `debug_pages`.
  NOTE: if you pass an **int**, it is treated as 1-based (human page number).
        if you pass a **set[int]**, those are treated as 0-based indices.

Public API:
    - extract_text_whole(path, debug=False, debug_pages: int|set[int]|None=None) -> str
    - extract_pdf_text(path, debug=False, debug_pages: int|set[int]|None=None) -> str
    - count_pages(pdf_path) -> int
    - infer_decision_number(text_norm) -> str|None
"""

from __future__ import annotations

import contextlib
import logging
import math
import os
import re
import statistics
from collections import defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass, field

# pdfminer.six
from pdfminer.high_level import extract_pages
from pdfminer.layout import (
    LTFigure,
    LTLayoutContainer,
    LTPage,
    LTTextBox,
    LTTextBoxHorizontal,
    LTTextContainer,
    LTTextLine,
    LTTextLineHorizontal,
)
from pdfminer.pdfdocument import PDFTextExtractionNotAllowed

from ..parsing.headers import parse_fek_header

__all__ = [
    "extract_text_whole",
    "extract_pdf_text",
    "count_pages",
    "infer_decision_number",
    "ColumnExtractor",
    "PageContext",
    "_iter_lines",
    "extract_fek_header_meta",
]

log = logging.getLogger(__name__)

# ------------------------------- Typing ------------------------------------ #

_PathLike = str | bytes | os.PathLike[str]


def _to_str_path(p: _PathLike) -> str:
    s = os.fspath(p)
    return s if isinstance(s, str) else s.decode()  # utf-8


# ------------------------------- Utilities --------------------------------- #

Line = tuple[float, float, float, float, str]  # (x0, y0, x1, y1, text)


def _clean_text(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = s.replace("\t", " ")
    s = s.strip()
    while "  " in s:
        s = s.replace("  ", " ")
    return s


def _iter_lines(layout: LTLayoutContainer) -> Iterator[Line]:
    for element in layout:
        if isinstance(element, LTTextBox | LTTextBoxHorizontal | LTTextContainer):
            for obj in element:
                if isinstance(obj, LTTextLine | LTTextLineHorizontal):
                    txt = _clean_text(obj.get_text())
                    if txt:
                        x0, y0, x1, y1 = obj.bbox
                        if x1 < x0:
                            x0, x1 = x1, x0
                        if y1 < y0:
                            y0, y1 = y1, y0
                        yield (x0, y0, x1, y1, txt)
        elif isinstance(element, LTFigure):
            yield from _iter_lines(element)
        # ignore drawing primitives


# --- Header/Footer filtering (improved) ------------------------------------ #

# "ΕΦΗΜΕΡΙΔΑ ΤΗΣ ΚΥΒΕΡΝΗΣΕΩΣ" (Δ may appear as '∆', Τ may be latin 'T')
_ET_GAZETTE_RE = re.compile(r"ΕΦΗΜΕΡΙ[∆Δ]Α\s+[TΤ]ΗΣ\s+ΚΥΒΕΡΝΗΣΕΩΣ", re.IGNORECASE)
# "Τεύχος A’ 136/17.07.2020" or similar
_ISSUE_RE = re.compile(r"^\s*Τεύχος\b", re.IGNORECASE)
# Site/emails that only appear in headers/footers/backmatter
_SITE_RE = re.compile(r"(www\.et\.gr|helpdesk\.et@et\.gr|webmaster\.et@et\.gr)", re.IGNORECASE)
_CONTACT_RE = re.compile(r"(Καποδιστρίου|ΤΗΛΕΦΩΝΙΚΟ\s+ΚΕΝΤΡΟ|ΕΞΥΠΗΡΕΤΗΣΗ\s+ΚΟΙΝΟΥ)", re.IGNORECASE)
# bare page number like "3007"
_PAGE_NUM_RE = re.compile(r"^\s*\d{3,5}\s*$")
# Barcode-like footer lines (π.χ. *01001951708070040*)
_BARCODE_RE = re.compile(r"^\s*\*?\s*\d{12,}\s*\*?\s*$")

# FEK page counters like "4180−6" that use non-ASCII dashes (en/em/minus/etc.)
_NONASCII_DASHES = "\u2012\u2013\u2014\u2212\u2010\u2011"
_PAGE_COUNTER_RE = re.compile(rf"^\s*\d{{3,5}}\s*[{_NONASCII_DASHES}]\s*\d{{1,2}}\s*$")
# Inline token version (in case a counter gets merged inside a text line)
_INLINE_PAGE_COUNTER_RE = re.compile(
    rf"(?<!\d)\b\d{{3,5}}\s*[{_NONASCII_DASHES}]\s*\d{{1,2}}\b(?!\d)",
    re.UNICODE,
)


def _is_header_footer_line(line: Line, _page_w: float, page_h: float) -> bool:
    _x0, y0, _x1, y1, t = line
    if not t:
        return False

    ts = t.strip()

    # Strong match: remove anywhere
    if _ET_GAZETTE_RE.search(ts) or ("ΕΦΗΜΕΡΙ" in ts and "ΚΥΒΕΡΝΗΣ" in ts):
        return True

    # NEW: barcode-like lines (συνήθως κάτω-κάτω)
    if _BARCODE_RE.match(ts):
        return True

    # Generous bands (headers often sit deeper than 93%)
    top_band = (y1 >= 0.88 * page_h) or (y0 >= 0.86 * page_h)
    bot_band = (y0 <= 0.12 * page_h) or (y1 <= 0.14 * page_h)
    if not (top_band or bot_band):
        return False

    if _ISSUE_RE.search(ts):
        return True
    if _SITE_RE.search(ts):
        return True
    if _CONTACT_RE.search(ts):
        return True
    return bool(_PAGE_NUM_RE.match(ts) or _PAGE_COUNTER_RE.match(ts))


def _filter_headers_footers(lines: list[Line], page_w: float, page_h: float) -> list[Line]:
    return [ln for ln in lines if not _is_header_footer_line(ln, page_w, page_h)]


def extract_fek_header_meta(path: _PathLike, pages_to_scan: int = 2) -> dict[str, str]:
    """
    Διαβάζει ΜΟΝΟ τα header/footer των πρώτων σελίδων και εξάγει
    fek_series, fek_number, fek_date, fek_date_iso με το parse_fek_header.
    """
    texts: list[str] = []

    for page_index, layout in enumerate(extract_pages(_to_str_path(path))):
        if page_index >= pages_to_scan:
            break
        if not isinstance(layout, LTPage):
            continue
        w, h = layout.width, layout.height

        # Μαζεύουμε μόνο τα header/footer (δηλ. αυτά που θα έκοβε το φίλτρο)
        for _x0, y0, _x1, y1, t in _iter_lines(layout):
            if t and _is_header_footer_line((_x0, y0, _x1, y1, t), w, h):
                texts.append(t.strip())

    blob = "\n".join(texts)
    meta = parse_fek_header(blob)
    return meta


# ----------------------- Column split (safer) ------------------------------ #


def _kmeans2_1d(xs: list[float], iters: int = 12) -> tuple[float, float, int, int, float] | None:
    if len(xs) < 6:
        return None
    xs = sorted(xs)
    c1, c2 = xs[0], xs[-1]
    left: list[float] = []
    right: list[float] = []
    for _ in range(iters):
        left.clear()
        right.clear()
        for x in xs:
            (left if abs(x - c1) <= abs(x - c2) else right).append(x)
        if not left or not right:
            return None
        n1 = sum(left) / len(left)
        n2 = sum(right) / len(right)
        if abs(n1 - c1) + abs(n2 - c2) < 0.5:
            c1, c2 = n1, n2
            break
        c1, c2 = n1, n2

    var1 = statistics.pvariance(left) if len(left) > 1 else 0.0
    var2 = statistics.pvariance(right) if len(right) > 1 else 0.0
    pooled = (var1 * (len(left) - 1) + var2 * (len(right) - 1)) / max(
        1, (len(left) + len(right) - 2)
    )
    return (min(c1, c2), max(c1, c2), len(left), len(right), max(pooled, 1e-6))


def _vertical_occupancy_split(
    lines: list[Line], page_w: float, _page_h: float, y_cut: float
) -> float | None:
    bins = max(48, int(page_w // 10))
    if bins <= 0:
        return None
    hist = [0.0] * bins

    for x0, y0, x1, y1, _t in lines:
        if y1 <= y_cut:
            continue
        b0 = max(0, min(bins - 1, int(bins * (x0 / page_w))))
        b1 = max(0, min(bins - 1, int(bins * (x1 / page_w))))
        h = max(0.0, y1 - y0)
        lo, hi = (b0, b1) if b0 <= b1 else (b1, b0)
        for b in range(lo, hi + 1):
            hist[b] += h

    if not any(hist):
        return None

    w = 5
    sm = [0.0] * bins
    for i in range(bins):
        j0 = max(0, i - w)
        j1 = min(bins - 1, i + w)
        sm[i] = sum(hist[j0 : j1 + 1]) / max(1, (j1 - j0 + 1))

    mid_lo = int(0.40 * bins)
    mid_hi = int(0.60 * bins)
    if mid_hi <= mid_lo:
        return None
    segment = list(enumerate(sm[mid_lo:mid_hi], start=mid_lo))
    min_pair = min(segment, key=lambda t: t[1])
    min_idx = int(min_pair[0])
    min_val = float(min_pair[1])

    med = statistics.median(sm)
    depth_ok = min_val <= 0.5 * med
    thr = 0.75 * med
    L = min_idx
    while L > 0 and sm[L] <= thr:
        L -= 1
    R = min_idx
    while bins - 1 > R and sm[R] <= thr:
        R += 1
    width_ok = ((R - L) / bins) >= 0.06

    if not (depth_ok and width_ok):
        return None

    return (float(min_idx) / float(bins)) * float(page_w)


def _choose_split_x(
    narrow_lines: list[Line], page_w: float, _page_h: float, y_cut: float
) -> float | None:
    if not narrow_lines:
        return None
    mids = [(x0 + x1) / 2.0 for (x0, _y0, x1, _y1, _t) in narrow_lines]
    km = _kmeans2_1d(mids)
    if km is None:
        return None
    cL, cR, nL, nR, pooled_var = km
    gap = cR - cL
    min_gap_pts = max(72.0, 0.14 * page_w)
    if gap < min_gap_pts or nL < 3 or nR < 3:
        return None
    if gap / math.sqrt(pooled_var) < 2.0:
        return None

    split_from_valley = _vertical_occupancy_split(narrow_lines, page_w, _page_h, y_cut)
    if split_from_valley is not None:
        return split_from_valley
    return (cL + cR) / 2.0


# --------------------------- Sticky smoothing ------------------------------ #


@dataclass
class SplitSmoother:
    """Rolling median split per (w,h,rotation) signature."""

    window: int = 7
    store: dict[tuple[int, int, int], deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=7))
    )

    @staticmethod
    def _sig(w: float, h: float, rot: int) -> tuple[int, int, int]:
        return (int(round(w)), int(round(h)), int(rot) % 360)

    def push(self, w: float, h: float, rot: int, split_x: float) -> None:
        ratio = split_x / max(1.0, w)
        self.store[self._sig(w, h, rot)].append(ratio)

    def median_for(self, w: float, h: float, rot: int) -> float | None:
        dq = self.store.get(self._sig(w, h, rot))
        if not dq:
            return None
        return statistics.median(dq)

    def suggest(
        self, w: float, h: float, rot: int, candidate_split: float, tolerance: float = 0.15
    ) -> float:
        med = self.median_for(w, h, rot)
        if med is None:
            return candidate_split
        cand_ratio = candidate_split / max(1.0, w)
        if abs(cand_ratio - med) > tolerance:
            return med * w
        return candidate_split


# --------------------------- Page processing -------------------------------- #


@dataclass
class PageContext:
    page_index: int
    width: float
    height: float
    rotation: int = 0
    page_count: int | None = None


ARTICLE_HEAD_RE = re.compile(r"^\s*Άρθρο\s+\d+\b", re.IGNORECASE)
GREEK_LOWER_START = re.compile(r"^[\u03B1-\u03C9\u1F00-\u1FFF]")
# Proclamation anchor (supports a few common verbs)
PROCLAIM_RE = re.compile(r"^\s*(Παραγγέλλ(?:ο|ου)με|Διατάσσουμε|Κηρύσσουμε)\b", re.IGNORECASE)

# Signature/date/seal anchors (when proclamation absent)
SIGNATURE_HEADER_RE = re.compile(
    r"^(?!.*[a-z\u03b1-\u03c9\u1F00-\u1FFF])\s*(?:"
    r"ΟΙ?\s+ΥΠΟΥΡΓΟΙ|"
    r"Ο\s+ΠΡΟΕΔΡΟΣ(?:\s+ΤΗΣ\s+ΔΗΜΟΚΡΑΤΙΑΣ)?|"
    r"Η\s+ΠΡΟΕΔΡΟΣ(?:\s+ΤΗΣ\s+ΔΗΜΟΚΡΑΤΙΑΣ)?|"
    r"Ο\s+ΥΠΟΥΡΓΟΣ|"
    r"Η\s+ΥΠΟΥΡΓΟΣ|"
    r"ΑΠΟ\s+ΤΟ\s+ΕΘΝΙΚΟ\s+ΤΥΠΟΓΡΑΦΕΙΟ"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)
DATE_LINE_RE = re.compile(
    r"^\s*(?:Αθήνα|ΑΘΗΝΑ),?\s*\d{1,2}(?:η|ης)?\s+[\u0370-\u03FF\u1F00-\u1FFF]+\s+\d{4}\b"
)
SEAL_LINE_RE = re.compile(r"^\s*Θεωρήθηκε\s+και\s+τέθηκε", re.IGNORECASE)

# Inline variants for trimming
DATE_INLINE_RE = re.compile(
    r"(?:^|[.\u00B7;,\s])(?:Αθήνα|ΑΘΗΝΑ),?\s*\d{1,2}(?:η|ης)?\s+[\u0370-\u03FF\u1F00-\u1FFF]+\s+\d{4}\b"
)
SIGNATURE_INLINE_RE = re.compile(
    r"\b(?:ΟΙ?\s+ΥΠΟΥΡΓΟΙ|Ο\s+ΠΡΟΕΔΡΟΣ(?:\s+ΤΗΣ\s+ΔΗΜΟΚΡΑΤΙΑΣ)?|Η\s+ΠΡΟΕΔΡΟΣ(?:\s+ΤΗΣ\s+ΔΗΜΟΚΡΑΤΙΑΣ)?)\b",
    re.IGNORECASE | re.UNICODE,
)
SEAL_INLINE_RE = re.compile(r"Θεωρήθηκε\s+και\s+τέθηκε", re.IGNORECASE | re.UNICODE)

# Headline (title-like) guard for unfinished-sentence demotion (allow Greek punctuation/marks)
HEAD_TITLE_RE = re.compile(r"^[A-ZΑ-ΩΊΌΎΈΉΏΪΫ \-–’'\"·\u0374\u0384\u02BC]+$")


def _looks_titleish(s: str) -> bool:
    ts = (s or "").strip()
    if len(ts) < 2 or len(ts) > 60:
        return False
    if any(ch.isdigit() for ch in ts):
        return False
    return not any(p in ts for p in ".:;·•—–")


def _is_signatureish(line_text: str) -> bool:
    ts = (line_text or "").strip()
    if not ts:
        return False
    if PROCLAIM_RE.match(ts):
        return True
    if SIGNATURE_HEADER_RE.match(ts):
        return True
    if DATE_LINE_RE.match(ts):
        return True
    return bool(SEAL_LINE_RE.match(ts))


# ANNEX detection
_ROMAN_CLASS = r"(?:[IVXLCDMΙΧ]+|[Ⅰ-Ⅿⅰ-ⅿ]+)"
ANNEX_HEADING_RE = re.compile(rf"^\s*ΠΑΡΑΡΤΗΜΑ(?:\s+{_ROMAN_CLASS})?\b", re.UNICODE)


def _is_annex_heading_line(txt: str) -> bool:
    if not txt:
        return False
    m = ANNEX_HEADING_RE.match(txt)
    if not m:
        return False
    after = (txt[m.end() :] or "").lstrip()
    return not re.match(r"^(του|της|των)\b", after, flags=re.IGNORECASE | re.UNICODE)


# --- TOC detection helpers --------------------------------------------------
SECTION_HEADING_RE = re.compile(r"^\s*(ΜΕΡΟΣ|ΚΕΦΑΛΑΙΟ)\b", re.UNICODE)


def _page_looks_like_toc(lines: list[Line], split_x: float | None, page_w: float) -> bool:
    """
    Heuristic: Πολλές κεφαλίδες 'Άρθρο N' σε full-width + μερικά 'ΜΕΡΟΣ/ΚΕΦΑΛΑΙΟ'
    υποδηλώνουν TOC. Δεν αλλάζουμε ταξινόμηση, απλά απενεργοποιούμε τις demotions.
    """
    if split_x is None:
        return False

    heads = 0
    wide_heads = 0
    sections = 0
    PAD = 2.0
    for x0, _y0, x1, _y1, t in lines:
        s = t or ""
        if ARTICLE_HEAD_RE.match(s):
            heads += 1
            crosses = (x0 + PAD) < split_x and (x1 - PAD) > split_x
            is_wide = (x1 - x0) >= 0.80 * page_w or crosses
            if is_wide:
                wide_heads += 1
        elif SECTION_HEADING_RE.match(s) and s.isupper():
            sections += 1

    if heads >= 6 and wide_heads >= 5:
        return True
    return bool(heads >= 4 and sections >= 2)


def _overlap_len(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


class ColumnExtractor:
    """
    Stateful extractor using sticky split across pages.
    Only three buckets: left, right, tail (single-column after both columns end).
    """

    def __init__(self, debug: bool = False, debug_pages: set[int] | None = None) -> None:
        self.prev_split_x: float | None = None
        self.prev_w: float | None = None
        self.smoother = SplitSmoother()
        self.debug = debug
        self.debug_pages = set(debug_pages or set())
        self.terminal_reached: bool = False
        self.seen_any_article: bool = False
        self._seen_article_numbers: set[int] = set()

    def _dprint(self, ctx: PageContext, *args: object) -> None:
        if self.debug and (not self.debug_pages or ctx.page_index in self.debug_pages):
            print(*args)

    def process_page(self, ctx: PageContext, lines: list[Line]) -> str:
        """
        Two-column detection with tail handling, header/footer stripping,
        safe demotions, and tail trimming. Sets terminal_reached=True only when
        a true terminal anchor was trimmed on this page (not for demotions).
        """
        self.terminal_reached = False  # reset for this page

        w, h, rot = ctx.width, ctx.height, ctx.rotation

        # 0) strip header/footer first
        lines = _filter_headers_footers(lines, w, h)

        # Track if this page has an article head; remember globally (for TOC guard)
        page_has_article = any(ARTICLE_HEAD_RE.match(ln[4] or "") for ln in lines)
        if page_has_article:
            self.seen_any_article = True

        # 1) collect narrow lines for split detection
        WIDE_FRAC = 0.70
        PAD = 2.0
        narrow_for_split: list[Line] = []
        for x0, y0, x1, y1, t in lines:
            if (x1 - x0) < WIDE_FRAC * w:
                narrow_for_split.append((x0, y0, x1, y1, t))

        split_x = _choose_split_x(narrow_for_split, w, h, 0.0)

        # sticky reuse + smoothing
        if (
            split_x is None
            and self.prev_split_x is not None
            and self.prev_w
            and abs(self.prev_w - w) < 0.5
        ):
            split_x = self.prev_split_x
        if split_x is not None:
            split_x = self.smoother.suggest(w, h, rot, split_x)
            self.smoother.push(w, h, rot, split_x)

        # TOC-like page? (disable demotions on this page only)
        is_toc_page = _page_looks_like_toc(lines, split_x, w)
        if is_toc_page:
            self._dprint(
                ctx,
                f"[pdf][toc] Page {ctx.page_index+1}: " "TOC-like page — demotions disabled",
            )

        # If no reliable split → just 1-column; still apply ANNEX/trim logic
        if split_x is None:
            ordered = sorted(lines, key=lambda L: (-L[3], L[0]))

            # Last article y on this page
            last_head_y_1col: float | None = None
            for ln in ordered:
                if ARTICLE_HEAD_RE.match(ln[4] or ""):
                    y_mid = (ln[1] + ln[3]) / 2.0
                    if last_head_y_1col is None or y_mid < last_head_y_1col:
                        last_head_y_1col = y_mid

            # ANNEX cut
            annex_cut_y_1col: float | None = None
            if last_head_y_1col is not None:
                for ln in ordered:
                    if _is_annex_heading_line(ln[4] or ""):
                        ym = (ln[1] + ln[3]) / 2.0
                        if ym < last_head_y_1col:
                            annex_cut_y_1col = ym
                            break
            elif self.seen_any_article:
                for ln in ordered:
                    if _is_annex_heading_line(ln[4] or ""):
                        annex_cut_y_1col = (ln[1] + ln[3]) / 2.0
                        break

            if annex_cut_y_1col is not None:
                kept = [
                    ln
                    for ln in ordered
                    if ((ln[1] + ln[3]) / 2.0) > annex_cut_y_1col
                    and not _is_annex_heading_line(ln[4] or "")
                ]
                self.terminal_reached = True
                return _lines_to_text(kept)

            # signature/date/proclamation cut (below last head)
            if last_head_y_1col is not None:
                sig_cut_y: float | None = None
                for ln in ordered:
                    y_mid = (ln[1] + ln[3]) / 2.0
                    if y_mid >= last_head_y_1col:
                        continue
                    txt = ln[4] or ""
                    if PROCLAIM_RE.match(txt) or _is_signatureish(txt):
                        sig_cut_y = y_mid
                        break
                if sig_cut_y is not None:
                    kept = [
                        ln
                        for ln in ordered
                        if ((ln[1] + ln[3]) / 2.0) > sig_cut_y
                        and not PROCLAIM_RE.match(ln[4] or "")
                        and not _is_annex_heading_line(ln[4] or "")
                    ]
                    self.terminal_reached = True
                    return _lines_to_text(kept)

            return _lines_to_text(ordered)

        # With split: estimate bottoms of columns and gather any pre-tail lines
        L0, L1 = 0.0 + PAD, split_x - PAD
        R0, R1 = split_x + PAD, w - PAD

        def _frac_overlap(x0: float, x1: float, a0: float, a1: float) -> float:
            den = max(0.0, a1 - a0)
            if den <= 0:
                return 0.0
            return _overlap_len(x0, x1, a0, a1) / den

        # Provisional per-column bottoms from all lines (non-heads) roughly in each column
        left_ys: list[float] = []
        right_ys: list[float] = []
        for x0, y0, x1, y1, t in lines:
            ts = t or ""
            if ARTICLE_HEAD_RE.match(ts):
                continue
            fracL = _frac_overlap(x0, x1, L0, L1)
            fracR = _frac_overlap(x0, x1, R0, R1)
            y_mid = (y0 + y1) / 2.0
            if (fracL >= 0.55) and (fracR <= 0.35):
                left_ys.append(y_mid)
            elif (fracR >= 0.55) and (fracL <= 0.35):
                right_ys.append(y_mid)

        bottom_left = min(left_ys) if left_ys else float("inf")
        bottom_right = min(right_ys) if right_ys else float("inf")
        TAIL_Y_CUTOFF = min(bottom_left, bottom_right) - 1.0

        # Cushion: push the cutoff DOWN so end-of-page lines aren’t tailed
        # ~20pt minimum, scaled by page height (2% of h)
        TAIL_CUTOFF_CUSHION_PT = max(20.0, 0.02 * h)

        # --- First pass: anything strictly below both columns → tail
        tail: list[Line] = []
        non_tail: list[Line] = []

        for ln in lines:
            x0, y0, x1, y1, t = ln
            y_mid = (y0 + y1) / 2.0
            if y_mid <= TAIL_Y_CUTOFF - TAIL_CUTOFF_CUSHION_PT:
                tail.append(ln)
            else:
                non_tail.append(ln)

        # Classify remaining into left/right (no wide buckets)
        left: list[Line] = []
        right: list[Line] = []
        for x0, y0, x1, y1, t in non_tail:
            fracL = _frac_overlap(x0, x1, L0, L1)
            fracR = _frac_overlap(x0, x1, R0, R1)
            if (fracL >= 0.60) and (fracR <= 0.25):
                left.append((x0, y0, x1, y1, t))
            elif (fracR >= 0.60) and (fracL <= 0.25):
                right.append((x0, y0, x1, y1, t))
            else:
                mid = (x0 + x1) / 2.0
                (left if mid < split_x else right).append((x0, y0, x1, y1, t))

        left_sorted = sorted(left, key=lambda L: (-L[3], L[0]))
        right_sorted = sorted(right, key=lambda L: (-L[3], L[0]))
        tail_sorted = sorted(tail, key=lambda L: (-L[3], L[0]))

        # ---------------- Demotions into tail ----------------

        def _first_head_idx(lines_sorted: list[Line]) -> int | None:
            for i, (_x0, _y0, _x1, _y1, raw) in enumerate(lines_sorted):
                if ARTICLE_HEAD_RE.match(raw or ""):
                    return i
            return None

        def _ends_with_terminal(s: str) -> bool:
            if not s:
                return False
            ts = re.sub(r"[»”'\"\)\]\}]+$", "", s.strip())
            if ts.endswith("-"):
                return False
            return bool(re.search(r"[.\u00B7;!…]$", ts))

        def _bucket_demote_from_head_if_width_change(
            lines_sorted: list[Line], side: str
        ) -> tuple[list[Line], list[Line], bool]:
            # Σελίδα TOC; ποτέ demotion εδώ
            if is_toc_page:
                return lines_sorted, [], False

            i = _first_head_idx(lines_sorted)
            if i is None:
                return lines_sorted, [], False

            # Απαιτούμε «γερό» cross: σημαντική κάλυψη και στα δύο κανάλια
            CROSS_FRAC_MIN = 0.28  # τουλάχιστον 28% κάλυψη σε κάθε κανάλι
            CROSS_PAD = max(4.0, 0.01 * w)  # πιο «ακριβές» pad από το απλό PAD

            def crosses_strong(x0: float, x1: float) -> bool:
                # Πρέπει να διασχίζει ξεκάθαρα το split (με ασφάλεια CROSS_PAD)
                if not ((x0 + CROSS_PAD) < split_x and (x1 - CROSS_PAD) > split_x):
                    return False
                # Και να καλύπτει ουσιαστικό ποσοστό και του αριστερού και του δεξιού καναλιού
                lcov = _frac_overlap(x0, x1, L0, L1)
                rcov = _frac_overlap(x0, x1, R0, R1)
                return (lcov >= CROSS_FRAC_MIN) and (rcov >= CROSS_FRAC_MIN)

            # Ελέγχουμε τις 1–3 επόμενες γραμμές μετά τον πρώτο head της στήλης
            for j in range(i + 1, min(i + 4, len(lines_sorted))):
                x0, _y0, x1, _y1, raw = lines_sorted[j]
                s = (raw or "").strip()

                # Αγνόησε καθαρούς τίτλους/κεφαλίδες (ALL-CAPS, ΜΕΡΟΣ/ΚΕΦΑΛΑΙΟ)
                if (
                    (SECTION_HEADING_RE.match(s) and s.isupper()) or HEAD_TITLE_RE.match(s)
                ) and not _is_annex_heading_line(s):
                    continue

                if crosses_strong(x0, x1):
                    head_and_after = lines_sorted[i:]
                    before = lines_sorted[:i]
                    # Debug info για να δεις «γιατί» θεωρήθηκε cross
                    if self.debug and (not self.debug_pages or ctx.page_index in self.debug_pages):
                        lcov = _frac_overlap(x0, x1, L0, L1)
                        rcov = _frac_overlap(x0, x1, R0, R1)
                        self._dprint(
                            ctx,
                            (
                                f"[pdf][width-switch] Page {ctx.page_index+1} {side}: "
                                f"demoting {len(head_and_after)} line(s) to tail "
                                f"(triggered by j={j}, x0={x0:.1f}, x1={x1:.1f}, "
                                f"split={split_x:.1f}, "
                                f"Lcov={lcov:.2f}, Rcov={rcov:.2f})"
                            ),
                        )
                    return before, head_and_after, True

            return lines_sorted, [], False

        def _bucket_demote_if_unfinished_then_head(
            lines_sorted: list[Line],
            side: str,
        ) -> tuple[list[Line], list[Line], bool]:
            if is_toc_page:
                return lines_sorted, [], False
            if not self.seen_any_article:
                return lines_sorted, [], False
            i = _first_head_idx(lines_sorted)
            if i is None or i == 0:
                return lines_sorted, [], False
            # Find last meaningful line above
            last_txt = ""
            for j in range(i - 1, -1, -1):
                t = lines_sorted[j][4] or ""
                if not t:
                    continue
                if ARTICLE_HEAD_RE.match(t) or _is_annex_heading_line(t):
                    continue
                last_txt = t.strip()
                if last_txt:
                    break
            if not last_txt:
                return lines_sorted, [], False
            if _ends_with_terminal(last_txt) or HEAD_TITLE_RE.match(last_txt):
                return lines_sorted, [], False
            head_and_after = lines_sorted[i:]
            before = lines_sorted[:i]
            self._dprint(
                ctx,
                (
                    f"[pdf][break] Page {ctx.page_index+1} {side}: head after unfinished "
                    f"sentence → demoting {len(head_and_after)} line(s) to tail"
                ),
            )
            return before, head_and_after, True

        # Article-gap demotion
        HEAD_NUM_RE = re.compile(r"^\s*Άρθρο\s+(\d+)\b", re.IGNORECASE | re.UNICODE)

        def _heads_in(lines_sorted: list[Line]) -> list[int]:
            out: list[int] = []
            for _x0, _y0, _x1, _y1, raw in lines_sorted:
                m = HEAD_NUM_RE.match(raw or "")
                if m:
                    with contextlib.suppress(Exception):
                        out.append(int(m.group(1)))
            return out

        page_heads = set(_heads_in(left_sorted) + _heads_in(right_sorted) + _heads_in(tail_sorted))

        def _bucket_demote_on_true_gap(
            lines_sorted: list[Line],
            side: str,
        ) -> tuple[list[Line], list[Line], bool]:
            if is_toc_page:
                return lines_sorted, [], False
            prev = None
            cut = None
            trigger = None
            for i, (_x0, _y0, _x1, _y1, raw) in enumerate(lines_sorted):
                m = HEAD_NUM_RE.match(raw or "")
                if not m:
                    continue
                try:
                    n = int(m.group(1))
                except Exception:
                    continue
                if prev is None:
                    prev = n
                    continue
                if n >= prev + 2:
                    missing = set(range(prev + 1, n))
                    if missing.isdisjoint(page_heads) and missing.isdisjoint(
                        self._seen_article_numbers
                    ):
                        cut = i
                        trigger = n
                        break
                prev = max(prev, n)
            if cut is None:
                return lines_sorted, [], False
            head_and_after = lines_sorted[cut:]
            before = lines_sorted[:cut]
            self._dprint(
                ctx,
                (
                    f"[pdf][gap] Page {ctx.page_index+1} {side}: TRUE GAP prev→curr "
                    f"triggers demotion of {len(head_and_after)} line(s) to tail "
                    f"(trigger={trigger})"
                ),
            )
            return before, head_and_after, True

        # Apply demotions in priority order: width-switch → unfinished → gap
        left_sorted, extra_tail, moved = _bucket_demote_from_head_if_width_change(
            left_sorted, "LEFT"
        )
        if moved and extra_tail:
            tail_sorted = extra_tail + tail_sorted
        if not moved:
            left_sorted, extra_tail, moved = _bucket_demote_if_unfinished_then_head(
                left_sorted, "LEFT"
            )
            if moved and extra_tail:
                tail_sorted = extra_tail + tail_sorted
        left_sorted, extra_tail, moved2 = _bucket_demote_on_true_gap(left_sorted, "LEFT")
        if moved2 and extra_tail:
            tail_sorted = extra_tail + tail_sorted

        # Update seen article numbers after processing this page
        self._seen_article_numbers.update(page_heads)

        # --------- ANNEX terminal: stop emitting from the first ANNEX heading and after ----------
        def _first_annex_y_pre() -> float | None:
            # Search BEFORE dropping annex headings
            all_lines_pre = sorted(
                left_sorted + right_sorted + tail_sorted, key=lambda L: (-L[3], L[0])
            )
            for _x0, y0, _x1, y1, raw in all_lines_pre:
                if _is_annex_heading_line(raw or ""):
                    return (y0 + y1) / 2.0
            return None

        annex_cut_y = _first_annex_y_pre()
        if annex_cut_y is not None:

            def _split_annex(lines_sorted: list[Line]) -> list[Line]:
                above: list[Line] = []
                for ln in lines_sorted:
                    ym = (ln[1] + ln[3]) / 2.0
                    if ym > annex_cut_y:  # keep only content ABOVE the ANNEX heading
                        above.append(ln)
                return above

            left_sorted = _split_annex(left_sorted)
            right_sorted = _split_annex(right_sorted)
            tail_sorted = _split_annex(tail_sorted)
            # Stop after this page; remaining pages are Annex
            self.terminal_reached = True

        # Drop ANNEX headings from emission
        def _drop_annex(lines_sorted: list[Line]) -> list[Line]:
            out: list[Line] = []
            for x0, y0, x1, y1, raw in lines_sorted:
                txt = raw or ""
                if _is_annex_heading_line(txt):
                    continue
                out.append((x0, y0, x1, y1, txt))
            return out

        left_sorted = _drop_annex(left_sorted)
        right_sorted = _drop_annex(right_sorted)
        tail_sorted = _drop_annex(tail_sorted)

        # ---------------- Global full-width switch to single-column tail ----
        # If a truly full-width line appears (spans both columns with sizable overlap
        # OR is >= 92% page width), then EVERYTHING at or below that y goes to the tail.
        # Ignored on TOC-like pages and for header-ish lines (Άρθρο/ΜΕΡΟΣ/ΚΕΦΑΛΑΙΟ/title-ish).
        if split_x is not None and not is_toc_page:
            COL_CROSS_MIN_FRAC = 0.28  # at least ~28% της κάθε στήλης σε κάθε πλευρά

            def _is_headerish(s: str) -> bool:
                if not s:
                    return False
                if ARTICLE_HEAD_RE.match(s):
                    return True
                if SECTION_HEADING_RE.match(s) and s.isupper():
                    return True
                return bool(HEAD_TITLE_RE.match(s.strip()))

            def _first_fullwidth_y_all() -> tuple[float, str] | tuple[None, None]:
                # γεωμετρία στηλών
                col_w = max(1.0, min(L1 - L0, R1 - R0))
                all_non_tail = sorted(left_sorted + right_sorted, key=lambda L: (-L[3], L[0]))
                for x0, y0, x1, y1, t in all_non_tail:
                    s = t or ""
                    if _is_headerish(s):
                        continue

                    # overlap με κάθε στήλη
                    overL = _overlap_len(x0, x1, L0, L1)
                    overR = _overlap_len(x0, x1, R0, R1)
                    crosses_strong = (overL >= COL_CROSS_MIN_FRAC * col_w) and (
                        overR >= COL_CROSS_MIN_FRAC * col_w
                    )

                    # εναλλακτικό: πραγματικά τεράστιο πλάτος
                    is_very_wide = (x1 - x0) >= 0.92 * w

                    if crosses_strong or is_very_wide:
                        return ((y0 + y1) / 2.0, s)
                return (None, None)

            cut_y, trigger_txt = _first_fullwidth_y_all()
            if cut_y is not None:
                # Split buckets at the trigger y
                def _split_by_y(lines_sorted: list[Line]) -> tuple[list[Line], list[Line]]:
                    above: list[Line] = []
                    below: list[Line] = []
                    for x0, y0, x1, y1, txt in lines_sorted:
                        ym = (y0 + y1) / 2.0
                        (below if ym <= cut_y else above).append((x0, y0, x1, y1, txt))
                    return above, below

                left_above, left_below = _split_by_y(left_sorted)
                right_above, right_below = _split_by_y(right_sorted)

                # (a) Has an article head already appeared above this cut on this page?
                def _has_head_above(lines_sorted: list[Line]) -> bool:
                    for _x0, y0, _x1, y1, t in lines_sorted:
                        if ARTICLE_HEAD_RE.match(t or "") and (y0 + y1) / 2.0 > cut_y:
                            return True
                    return False

                has_head_above = _has_head_above(left_above) or _has_head_above(right_above)

                # (b) Is the trigger likely a masthead/issue banner?
                def _is_mastheadish(s: str) -> bool:
                    if not s:
                        return False
                    s2 = (s or "").strip()
                    # very uppercase Greek-ish text?
                    letters = [ch for ch in s2 if ch.isalpha()]
                    if letters:
                        up_ratio = sum(ch == ch.upper() for ch in letters) / len(letters)
                    else:
                        up_ratio = 0.0
                    # typical Gazette tokens
                    has_gov = "ΕΛΛΗΝΙΚ" in s2 and "ΔΗΜΟΚΡΑΤ" in s2
                    has_issue = "Αρ." in s2 and "Φύλλ" in s2
                    has_series = "ΤΕΥΧΟΣ" in s2
                    return (up_ratio >= 0.90) and (has_gov or has_issue or has_series)

                # (c) Require non-trivial two-column content already ABOVE the cut
                min_above = 6  # tune 4–8 if needed
                above_count = len(left_above) + len(right_above)

                # Final condition: demote only if (enough above OR an article head above),
                # and the trigger is not mastheadish
                should_demote = (
                    (above_count >= min_above) or has_head_above
                ) and not _is_mastheadish(trigger_txt or "")

                moved_lines: list[Line] = left_below + right_below
                if should_demote and moved_lines:
                    self._dprint(
                        ctx,
                        (
                            f"[pdf][global-width→tail] Page {ctx.page_index+1}: "
                            f"full-width detected (trigger='{(trigger_txt or '')[:60]}…') "
                            f"→ moving {len(moved_lines)} line(s) to tail"
                        ),
                    )
                    left_sorted = left_above
                    right_sorted = right_above
                    tail_sorted = sorted(
                        tail_sorted + moved_lines,
                        key=lambda L: (-L[3], L[0]),
                    )

        # ---------------- Late pickup / demotions for terminal & full-width ----
        # If a proclamation/signature/date line OR a late full-width line appears
        # inside LEFT/RIGHT (even if no head remains there), move from that line
        # downwards to the tail.

        def _last_head_y_bucket(lines_sorted: list[Line]) -> float | None:
            y: float | None = None
            for _x0, y0, _x1, y1, raw in lines_sorted:
                if ARTICLE_HEAD_RE.match(raw or ""):
                    ym = (y0 + y1) / 2.0
                    y = ym if (y is None or ym > y) else y
            return y

        def _pickup_terminal_to_tail(
            lines_sorted: list[Line], side: str
        ) -> tuple[list[Line], list[Line], bool]:
            if not lines_sorted:
                return lines_sorted, [], False
            last_head_y = _last_head_y_bucket(lines_sorted)

            for i, (x0, y0, x1, y1, raw) in enumerate(lines_sorted):
                txt = raw or ""
                ym = (y0 + y1) / 2.0

                # If there *is* a last head, only consider lines below it.
                # If there is NO head in this bucket, we still consider all lines,
                # because terminal blocks may have been separated earlier.
                if last_head_y is not None and ym >= last_head_y:
                    continue

                # strong anchors
                if PROCLAIM_RE.match(txt) or _is_signatureish(txt):
                    before = lines_sorted[:i]
                    moved = lines_sorted[i:]
                    self._dprint(
                        ctx,
                        (
                            f"[pdf][terminal→tail] Page {ctx.page_index+1} {side}: "
                            f"moving {len(moved)} line(s) to tail"
                        ),
                    )
                    return before, moved, True

                # inline variants: keep prefix and move rest
                m_inline = (
                    SIGNATURE_INLINE_RE.search(txt)
                    or DATE_INLINE_RE.search(txt)
                    or SEAL_INLINE_RE.search(txt)
                )
                if m_inline:
                    before = lines_sorted[:i]
                    prefix = txt[: m_inline.start()].rstrip(" ,.;·:")
                    keep_line = (x0, y0, x1, y1, prefix) if prefix else None
                    moved_first = (x0, y0, x1, y1, txt[m_inline.start() :].lstrip())
                    moved = [moved_first] + lines_sorted[i + 1 :]
                    if keep_line:
                        before.append(keep_line)
                    self._dprint(
                        ctx,
                        (
                            f"[pdf][terminal-inline→tail] Page {ctx.page_index+1} "
                            f"{side}: moving {len(moved)} line(s) to tail "
                            f"(kept prefix)"
                        ),
                    )
                    return before, moved, True

            return lines_sorted, [], False

        # First try direct terminal pickup (works even with no head in bucket)
        left_sorted, moved_tail, did_pick = _pickup_terminal_to_tail(left_sorted, "LEFT")
        if did_pick and moved_tail:
            tail_sorted += moved_tail
        right_sorted, moved_tail, did_pick = _pickup_terminal_to_tail(right_sorted, "RIGHT")
        if did_pick and moved_tail:
            tail_sorted += moved_tail

        # ---------------- Tail trimming (terminal anchors) ------------------
        def _trim_tail(lines_sorted: list[Line]) -> tuple[list[Line], bool]:
            if not lines_sorted:
                return lines_sorted, False
            last_head_y = _last_head_y_bucket(lines_sorted)
            out: list[Line] = []
            trimmed = False
            for x0, y0, x1, y1, raw in lines_sorted:
                txt = raw or ""
                ym = (y0 + y1) / 2.0
                below_ok = (last_head_y is not None and ym < last_head_y) or (last_head_y is None)
                if below_ok:
                    if (
                        PROCLAIM_RE.match(txt)
                        or SIGNATURE_HEADER_RE.match(txt)
                        or DATE_LINE_RE.match(txt)
                        or SEAL_LINE_RE.match(txt)
                    ):
                        trimmed = True
                        break
                    m_inline = (
                        SIGNATURE_INLINE_RE.search(txt)
                        or DATE_INLINE_RE.search(txt)
                        or SEAL_INLINE_RE.search(txt)
                    )
                    if m_inline:
                        prefix = txt[: m_inline.start()].rstrip(" ,.;·:")
                        if prefix:
                            out.append((x0, y0, x1, y1, prefix))
                        trimmed = True
                        break
                out.append((x0, y0, x1, y1, txt))
            return out, trimmed

        tail_sorted, did_trim_tail = _trim_tail(tail_sorted)
        if did_trim_tail:
            self.terminal_reached = True

        # ---------------- Emit (keep natural reading order) -----------------
        def _safe_text(lines_sorted: list[Line]) -> str:
            return _lines_to_text(lines_sorted)

        # Debug dump (only selected pages)
        if self.debug and (not self.debug_pages or ctx.page_index in self.debug_pages):
            print(
                f"[pdf][debug] Page {ctx.page_index+1}/{ctx.page_count or '?'} "
                "— emission after trims:"
            )

            def _dump_bucket(label: str, lines_sorted: list[Line]) -> None:
                print(f"  -- {label} ({len(lines_sorted)} lines) --")
                for i, (_x0, _y0, _x1, _y1, raw) in enumerate(lines_sorted):
                    t = raw or ""
                    print(f"    [{i:03d}] {t}")

            _dump_bucket("left", left_sorted)
            _dump_bucket("right", right_sorted)
            _dump_bucket("tail", tail_sorted)
            print(f"  terminal_reached on this page? {self.terminal_reached}")

        parts: list[str] = []
        if left_sorted:
            parts.append(_safe_text(left_sorted))
        if right_sorted:
            if parts:
                parts.append("")
            parts.append(_safe_text(right_sorted))
        if tail_sorted:
            if parts:
                parts.append("")
            parts.append(_safe_text(tail_sorted))

        # remember split for next page
        self.prev_split_x = split_x
        self.prev_w = w

        return "\n".join(parts).rstrip()


# --------------------------- Text joiner ----------------------------------- #


def _lines_to_text(lines: list[Line]) -> str:
    """
    Group nearby lines into paragraphs, join with newlines,
    and de-hyphenate simple word breaks (prev endswith '-' + next starts with Greek lowercase).
    """
    if not lines:
        return ""

    paras: list[list[str]] = []
    curr: list[str] = []
    last_y0: float | None = None
    last_y1: float | None = None

    def flush() -> None:
        if curr:
            paras.append(curr.copy())
            curr.clear()

    for _x0, y0, _x1, y1, t in sorted(lines, key=lambda L: (-L[3], L[0])):
        s = t or ""
        if last_y0 is None:
            curr.append(s)
            last_y0, last_y1 = y0, y1
            continue

        assert last_y0 is not None and last_y1 is not None
        ly0 = float(last_y0)
        ly1 = float(last_y1)
        vgap = ly0 - y1
        avg_height = max(1.0, (ly1 - ly0 + (y1 - y0)) / 2.0)

        if vgap > 0.6 * avg_height:
            flush()

        if curr and curr[-1].endswith("-") and GREEK_LOWER_START.match(s.lstrip()):
            curr[-1] = curr[-1][:-1] + s.lstrip()
        else:
            curr.append(s)

        last_y0, last_y1 = y0, y1

    flush()
    return "\n".join("\n".join(p) for p in paras if p)


def _debug_print_last_article(full_text: str) -> None:
    """
    Print the last 'Άρθρο N' block to stdout and also write it to
    'last_article_debug.txt' for inspection when debug=True.
    """
    try:
        matches = list(re.finditer(r"(?m)^\s*Άρθρο\s+(\d+)\b", full_text))
        if not matches:
            print("[pdf] No 'Άρθρο N' found in extracted text.")
            return

        last = matches[-1]
        start = last.start()
        block = full_text[start:].strip()

        # Helpful: check if an ANNEX heading still survives in this tail
        try:
            has_annex = bool(ANNEX_HEADING_RE.search(block))
        except NameError:
            has_annex = "ΠΑΡΑΡΤΗΜΑ" in block
        print("[pdf] Contains ANNEX heading?", has_annex)

    except Exception as e:
        print("[pdf] Debug print of last article failed:", e)


# --------------------------- Public API ----------------------------------- #


def extract_text_whole(
    path: _PathLike, debug: bool = False, debug_pages: int | set[int] | None = None
) -> str:
    """
    Iterate pages with ColumnExtractor, stop if a terminal anchor is hit,
    then (when debug=True) print/dump the last-article block for inspection.

    `debug_pages`:
      - int -> treated as **1-based** page number (human-friendly).
      - set[int] -> treated as **0-based** indices.
    """
    if isinstance(debug_pages, int):
        debug_pages_set = {max(0, debug_pages - 1)}
    elif isinstance(debug_pages, set):
        debug_pages_set = set(debug_pages)
    elif debug_pages is None:
        debug_pages_set = set()
    else:
        try:
            debug_pages_set = set(debug_pages)
        except Exception:
            debug_pages_set = set()

    extractor = ColumnExtractor(debug=debug, debug_pages=debug_pages_set)
    total_pages = count_pages(path) or 0
    out_pages: list[str] = []

    for page_index, layout in enumerate(extract_pages(_to_str_path(path))):
        if not isinstance(layout, LTPage):
            continue

        w, h = layout.width, layout.height
        rot = getattr(layout, "rotate", 0) or 0
        if rot % 180 != 0 and debug and (not debug_pages_set or page_index in debug_pages_set):
            print(f"[pdf] Page {page_index+1}: rotation={rot}° (split may be skipped)")

        lines = list(_iter_lines(layout))
        if not lines:
            out_pages.append("")
            continue

        ctx = PageContext(
            page_index=page_index, width=w, height=h, rotation=rot, page_count=total_pages
        )
        page_text = extractor.process_page(ctx, lines)
        out_pages.append(page_text)

        # Stop and drop remaining pages if terminal anchor detected on this page
        if extractor.terminal_reached:
            if debug and (not debug_pages_set or page_index in debug_pages_set):
                print(f"[pdf] Stop after page {page_index+1}: terminal anchor detected.")
            break

    full_text = "\n\n".join(out_pages).rstrip()

    if debug:
        _debug_print_last_article(full_text)

    return full_text


def extract_pdf_text(
    path: _PathLike, debug: bool = False, debug_pages: int | set[int] | None = None
) -> str:
    return extract_text_whole(path, debug=debug, debug_pages=debug_pages)


# ----------------------- Your originals (kept) ----------------------------- #


def count_pages(pdf_path: _PathLike) -> int:
    try:
        return sum(1 for _ in extract_pages(_to_str_path(pdf_path)))
    except PDFTextExtractionNotAllowed:
        log.warning("Page extraction not allowed for %s", pdf_path)
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("Failed to count pages for %s: %s", pdf_path, e)
        return 0


def infer_decision_number(text_norm: str) -> str | None:
    m_law = re.search(r"\bνομος\s+υπ\W*αριθ\W*(\d{1,6})\b", text_norm)
    if m_law:
        return m_law.group(1)
    m_any = re.search(r"(?i)\bαριθ[\.μ]*\s*(?P<num>\d{1,6})\b", text_norm)
    if m_any:
        return m_any.group("num")
    return None
