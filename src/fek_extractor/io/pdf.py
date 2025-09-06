# src/fek_extractor/io/pdf.py
"""
PDF text extraction with robust 2-column detection, safe single-column tail
(after columns), ET Gazette header/footer filtering, Greek de-hyphenation,
article heading clustering, and smart tail trimming:
- Trim from the first proclamation onward, OR
- If no proclamation, trim from the first signature/date/seal/ALL-CAPS block
  that appears after the last article block on the page, OR
- From a standalone ANNEX heading ("ΠΑΡΑΡΤΗΜΑ", optionally with Roman numeral)
  that appears after the last article block on the page.
- After we hit that end-of-document anchor on any page, drop ALL subsequent pages.

Public API (backward-compatible):
    - extract_text_whole(path: str | os.PathLike, debug: bool = False) -> str
    - count_pages(pdf_path: _PathLike) -> int
    - infer_decision_number(text_norm: str) -> str | None
"""

from __future__ import annotations

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
    # Old: return bool(_PAGE_NUM_RE.match(ts))
    # New: also accept FEK counters like "4180−6"
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
        # Use a normal deque at runtime; the annotation carries the value type.
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


ARTICLE_HEAD_RE = re.compile(r"^\s*Άρθρο\s+\d+\b", re.IGNORECASE)
GREEK_LOWER_START = re.compile(r"^[\u03B1-\u03C9\u1F00-\u1FFF]")
# Proclamation anchor (supports a few common verbs)
PROCLAIM_RE = re.compile(r"^\s*(Παραγγέλλ(?:ο|ου)με|Διατάσσουμε|Κηρύσσουμε)\b", re.IGNORECASE)

# Signature/date/seal anchors (when proclamation absent)
SIGNATURE_HEADER_RE = re.compile(
    r"^\s*(Οι\s+Υπουργοί|Ο\s+Υπουργός|Η\s+Υπουργός|Η\s+Πρόεδρος(?:\s+της\s+Δημοκρατίας)?|Ο\s+Πρόεδρος)\b",
    re.IGNORECASE,
)
DATE_LINE_RE = re.compile(r"^\s*Αθήνα,\s*\d{1,2}\s+[\u0370-\u03FF\u1F00-\u1FFF]+\s+\d{4}\b")
SEAL_LINE_RE = re.compile(r"^\s*Θεωρήθηκε\s+και\s+τέθηκε", re.IGNORECASE)

# ALL-CAPS (Greek) name-ish line (very common in signatures)
UPPER_GREEK_NAME_RE = re.compile(r"^[\u0386-\u03AB]{2,}(?:[\s\-–][\u0386-\u03AB]{2,})+$")

# ---------------------- ANNEX (ΠΑΡΑΡΤΗΜΑ) detection ------------------------ #
# Any lowercase (Latin or Greek)
LOWER_ANY_RE = re.compile(r"[a-z\u03B1-\u03C9\u1F00-\u1FFF]")

# Standalone structural heading: only “ΠΑΡΑΡΤΗΜΑ”
# Roman numerals: Latin IVXLCDM, Greek lookalikes Ι (iota), Χ (chi),
# and Unicode Roman numerals range (Ⅰ–Ⅿ, ⅰ–ⅿ)
_ROMAN_CLASS = r"(?:[IVXLCDMΙΧ]+|[Ⅰ-Ⅿⅰ-ⅿ]+)"

# Line that STARTS with "ΠΑΡΑΡΤΗΜΑ" and optional Roman, then word boundary
ANNEX_HEADING_RE = re.compile(rf"^\s*ΠΑΡΑΡΤΗΜΑ(?:\s+{_ROMAN_CLASS})?\b", re.UNICODE)


def _is_annex_heading_line(txt: str) -> bool:
    """
    True for a *real* ANNEX heading line:
      - line begins with 'ΠΑΡΑΡΤΗΜΑ' (+ optional Roman),
      - NOT the inline continuation case 'ΠΑΡΑΡΤΗΜΑ I του/της/των ...'.
    We NO LONGER reject headings just because lowercase appears later on the line.
    """
    if not txt:
        return False
    m = ANNEX_HEADING_RE.match(txt)
    if not m:
        return False
    after = (txt[m.end() :] or "").lstrip()
    # Inline continuation like: 'ΠΑΡΑΡΤΗΜΑ I του παρόντος ...'
    return not re.match(r"^(του|της|των)\b", after, flags=re.IGNORECASE | re.UNICODE)


def _looks_titleish(s: str) -> bool:
    """Heuristic: short, no digits, no trailing punctuation; e.g., 'Έναρξη ισχύος'."""
    ts = s.strip()
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
    if SEAL_LINE_RE.match(ts):
        return True
    return bool(UPPER_GREEK_NAME_RE.match(ts))


class ColumnExtractor:
    """
    Stateful extractor using sticky split across pages.
    Detects a *tail* single-column zone after the 2-column body and routes
    content (e.g., 'Άρθρο 93' and its subtitle) there so it appears after both columns.
    Also trims junk/signature/backmatter after the last article block.
    """

    def __init__(self, debug: bool = False) -> None:
        self.prev_split_x: float | None = None
        self.prev_w: float | None = None
        self.smoother = SplitSmoother()
        self.debug = debug
        # new: mark when we've hit the end-of-document anchor on this page
        self.terminal_reached: bool = False
        # NEW: track if we have seen any article on earlier pages
        self.seen_any_article: bool = False

    def _log(self, *args: object) -> None:
        if self.debug:
            print("[pdf]", *args)

    def process_page(self, ctx: PageContext, lines: list[Line]) -> str:
        """
        2-column detection with tail handling, header/footer stripping,
        article cluster promotion, and smart tail trimming.
        Also sets self.terminal_reached=True if this page contains an EOD anchor.
        """
        self.terminal_reached = False  # reset for this page

        w, h, rot = ctx.width, ctx.height, ctx.rotation

        # 0) strip header/footer first
        lines = _filter_headers_footers(lines, w, h)

        # Track if this page has an article head; remember globally
        page_has_article = any(ARTICLE_HEAD_RE.match(ln[4] or "") for ln in lines)
        if page_has_article:
            self.seen_any_article = True

        # 1) constants
        WIDE_FRAC = 0.70
        MARGIN_BELOW = 20.0  # cushion near 2-col bottom

        # helper: bottom of true 2-col zone (TOP of the main band)
        def _estimate_column_bottom(
            narrow: list[Line], split_x: float, w: float, h: float
        ) -> float:
            if not narrow:
                return float("inf")
            bins = max(48, int(h // 15))
            left_cnt = [0] * bins
            right_cnt = [0] * bins
            for x0, y0, x1, y1, _t in narrow:
                y_mid = (y0 + y1) / 2.0
                b = min(bins - 1, max(0, int(bins * (y_mid / h))))
                mid = (x0 + x1) / 2.0
                (left_cnt if mid < split_x else right_cnt)[b] += 1
            both = [1 if (left_cnt[i] > 0 and right_cnt[i] > 0) else 0 for i in range(bins)]
            for i in range(1, bins - 1):
                if both[i] == 0 and both[i - 1] and both[i + 1]:
                    both[i] = 1
            runs = []
            i = 0
            while i < bins:
                if both[i] == 1:
                    j = i
                    weight = 0
                    while j < bins and both[j] == 1:
                        weight += left_cnt[j] + right_cnt[j]
                        j += 1
                    runs.append((i, j - 1, j - i, weight))
                    i = j
                else:
                    i += 1
            if not runs:
                return float("inf")
            runs.sort(key=lambda r: (r[2], r[3]))
            low, _high, length, _weight = runs[-1]
            if length < max(4, int(0.08 * bins)):
                return float("inf")
            return (low / bins) * h

        # 2) narrow lines for split detection
        narrow_for_split: list[Line] = []
        for x0, y0, x1, y1, t in lines:
            if (x1 - x0) < WIDE_FRAC * w:
                narrow_for_split.append((x0, y0, x1, y1, t))

        y_cut_for_split = 0.0
        split_x = _choose_split_x(narrow_for_split, w, h, y_cut_for_split)

        # 3) sticky reuse + smoothing
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

        # 4) no reliable split → single-column
        if split_x is None:
            ordered = sorted(lines, key=lambda L: (-L[3], L[0]))
            if self.debug:
                self._log(f"Page {ctx.page_index}: 1-column (no reliable split)")

            # Compute last article head y (lowest on page)
            last_head_y_1col: float | None = None
            for ln in ordered:
                if ARTICLE_HEAD_RE.match(ln[4] or ""):
                    y_mid = (ln[1] + ln[3]) / 2.0
                    last_head_y_1col = (
                        y_mid
                        if (last_head_y_1col is None or y_mid < last_head_y_1col)
                        else last_head_y_1col
                    )

            # ANNEX cut (1-col): normal case (ANNEX below last article on same page)
            annex_cut_y_1col: float | None = None
            if last_head_y_1col is not None:
                for ln in ordered:
                    txt = ln[4] or ""
                    if _is_annex_heading_line(txt):
                        ym = (ln[1] + ln[3]) / 2.0
                        if ym < last_head_y_1col:
                            annex_cut_y_1col = ym
                            break
            # NEW: page after the last article — no article head on this page,
            # but we saw an article earlier → any ANNEX heading cuts.
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
                if self.debug:
                    self._log(
                        f"Page {ctx.page_index}: cut at ANNEX (1-col) y={annex_cut_y_1col:.1f}"
                    )
                self.terminal_reached = True
                return _lines_to_text(kept)

            # EOD detection even in 1-col: proclamation/signature anywhere?
            if any(
                PROCLAIM_RE.match(ln[4] or "") or _is_signatureish(ln[4] or "") for ln in ordered
            ):
                self.terminal_reached = True
            return _lines_to_text(ordered)

        # 5) tail detection
        y_bottom_cols = _estimate_column_bottom(narrow_for_split, split_x, w, h)
        have_tail_zone = y_bottom_cols != float("inf")

        # 6) classify
        left: list[Line] = []
        right: list[Line] = []
        wide_upper: list[Line] = []
        wide_lower: list[Line] = []
        tail_single: list[Line] = []

        if have_tail_zone:
            for x0, y0, x1, y1, t in lines:
                width = x1 - x0
                y_mid = (y0 + y1) / 2.0
                is_article_head = ARTICLE_HEAD_RE.match(t) is not None
                below_or_near_boundary = (y_mid < y_bottom_cols - MARGIN_BELOW) or (
                    is_article_head and abs(y_mid - y_bottom_cols) <= 24.0
                )
                if below_or_near_boundary:
                    if width >= WIDE_FRAC * w:
                        wide_lower.append((x0, y0, x1, y1, t))
                    else:
                        tail_single.append((x0, y0, x1, y1, t))
                else:
                    if width >= WIDE_FRAC * w:
                        wide_upper.append((x0, y0, x1, y1, t))
                    else:
                        mid = (x0 + x1) / 2.0
                        (left if mid < split_x else right).append((x0, y0, x1, y1, t))
        else:
            for x0, y0, x1, y1, t in lines:
                width = x1 - x0
                if width >= WIDE_FRAC * w:
                    wide_upper.append((x0, y0, x1, y1, t))
                else:
                    mid = (x0 + x1) / 2.0
                    (left if mid < split_x else right).append((x0, y0, x1, y1, t))

        # 6.5) Article cluster promotion — only when the head is already in the tail,
        # and there is tail evidence (proclamation/signature/date/seal) below.
        tail_evidence = any(
            PROCLAIM_RE.match(ln[4] or "") or _is_signatureish(ln[4] or "")
            for ln in (tail_single + wide_lower)
        )
        tail_heads: list[Line] = [
            ln for ln in (tail_single + wide_lower) if ARTICLE_HEAD_RE.match(ln[4] or "")
        ]
        if have_tail_zone and tail_evidence and tail_heads:
            y_head = max((ln[1] + ln[3]) / 2.0 for ln in tail_heads)
            for bucket in (left, right):
                keep: list[Line] = []
                for x0, y0, x1, y1, t in bucket:
                    y_mid = (y0 + y1) / 2.0
                    if (y_mid < y_head) and (y_head - y_mid <= 64.0) and _looks_titleish(t):
                        tail_single.append((x0, y0, x1, y1, t))
                    else:
                        keep.append((x0, y0, x1, y1, t))
                bucket[:] = keep

        # 7) fallback if unbalanced
        body_count = len(left) + len(right)
        starving = body_count >= 8 and (
            len(left) < max(3, 0.15 * body_count) or len(right) < max(3, 0.15 * body_count)
        )
        if starving:
            ordered = sorted(lines, key=lambda L: (-L[3], L[0]))
            if self.debug:
                self._log(
                    f"Page {ctx.page_index}: reverting to 1-column "
                    f"(unbalanced: L={len(left)} R={len(right)})"
                )

            # Try ANNEX cut in 1-col too (same as above)
            last_head_y_unbal: float | None = None
            for ln in ordered:
                if ARTICLE_HEAD_RE.match(ln[4] or ""):
                    y_mid = (ln[1] + ln[3]) / 2.0
                    last_head_y_unbal = (
                        y_mid
                        if (last_head_y_unbal is None or y_mid < last_head_y_unbal)
                        else last_head_y_unbal
                    )

            annex_cut_y_unbal: float | None = None
            if last_head_y_unbal is not None:
                for ln in ordered:
                    if _is_annex_heading_line(ln[4] or ""):
                        ym = (ln[1] + ln[3]) / 2.0
                        if ym < last_head_y_unbal:
                            annex_cut_y_unbal = ym
                            break
            elif self.seen_any_article:
                for ln in ordered:
                    if _is_annex_heading_line(ln[4] or ""):
                        annex_cut_y_unbal = (ln[1] + ln[3]) / 2.0
                        break

            if annex_cut_y_unbal is not None:
                kept = [
                    ln
                    for ln in ordered
                    if ((ln[1] + ln[3]) / 2.0) > annex_cut_y_unbal
                    and not _is_annex_heading_line(ln[4] or "")
                ]
                if self.debug:
                    self._log(
                        f"Page {ctx.page_index}: cut at ANNEX (1-col, unbalanced) "
                        f"y={annex_cut_y_unbal:.1f}"
                    )
                self.terminal_reached = True
                return _lines_to_text(kept)

            # EOD detection
            if any(
                PROCLAIM_RE.match(ln[4] or "") or _is_signatureish(ln[4] or "") for ln in ordered
            ):
                self.terminal_reached = True
            return _lines_to_text(ordered)

        # 8) sort within groups
        left_sorted = sorted(left, key=lambda L: (-L[3], L[0]))
        right_sorted = sorted(right, key=lambda L: (-L[3], L[0]))
        wide_upper_sorted = sorted(wide_upper, key=lambda L: (-L[3], L[0]))
        tail_single_sorted = sorted(tail_single, key=lambda L: (-L[3], L[0]))
        wide_lower_sorted = sorted(wide_lower, key=lambda L: (-L[3], L[0]))

        # -------------------- Smart tail trimming ----------------------------
        # Build a unified tail view and decide a cut anchor.
        tail_all = tail_single_sorted + wide_lower_sorted
        tail_all_sorted = sorted(tail_all, key=lambda L: (-L[3], L[0]))  # y1 desc, x0 asc

        # last article head position (visually lowest head on page)
        last_head_y_tail: float | None = None
        for ln in tail_all_sorted + left_sorted + right_sorted + wide_upper_sorted:
            if ARTICLE_HEAD_RE.match(ln[4] or ""):
                y_mid = (ln[1] + ln[3]) / 2.0
                last_head_y_tail = (
                    y_mid
                    if (last_head_y_tail is None or y_mid < last_head_y_tail)
                    else last_head_y_tail
                )

        y_cut: float | None = None
        cut_reason: str | None = None

        # Prefer proclamation
        for ln in tail_all_sorted:
            if PROCLAIM_RE.match(ln[4] or ""):
                y_cut = (ln[1] + ln[3]) / 2.0
                cut_reason = "proclaim"
                break

        # If no proclamation, standalone ANNEX heading AFTER the last article
        if y_cut is None and last_head_y_tail is not None:
            for ln in tail_all_sorted:
                txt = ln[4] or ""
                ym = (ln[1] + ln[3]) / 2.0
                if ym >= last_head_y_tail:  # only below the last article
                    continue
                if _is_annex_heading_line(txt):
                    y_cut = ym
                    cut_reason = "annex"
                    break

            # Fallback: ANNEX appeared in upper or columns but still after last article
            if y_cut is None:
                for ln in sorted(
                    wide_upper_sorted + left_sorted + right_sorted, key=lambda L: (-L[3], L[0])
                ):
                    txt = ln[4] or ""
                    ym = (ln[1] + ln[3]) / 2.0
                    if ym >= last_head_y_tail:
                        continue
                    if _is_annex_heading_line(txt):
                        y_cut = ym
                        cut_reason = "annex"
                        break

        # NEW: page has no article head but we’ve seen articles earlier → ANNEX anywhere cuts
        if y_cut is None and last_head_y_tail is None and self.seen_any_article:
            for ln in sorted(
                wide_upper_sorted + left_sorted + right_sorted + tail_all_sorted,
                key=lambda L: (-L[3], L[0]),
            ):
                if _is_annex_heading_line(ln[4] or ""):
                    y_cut = (ln[1] + ln[3]) / 2.0
                    cut_reason = "annex"
                    break

        # If still nothing, signature/date/seal after last head
        if y_cut is None:
            for ln in tail_all_sorted:
                y_mid = (ln[1] + ln[3]) / 2.0
                if last_head_y_tail is not None and y_mid >= last_head_y_tail:
                    continue
                if _is_signatureish(ln[4]):
                    y_cut = y_mid
                    cut_reason = "signature"
                    break

        # If still nothing, first ALL-CAPS run (>=2)
        if y_cut is None and last_head_y_tail is not None:
            caps_run = []
            for ln in tail_all_sorted:
                y_mid = (ln[1] + ln[3]) / 2.0
                if y_mid >= last_head_y_tail:
                    continue
                is_caps = bool(UPPER_GREEK_NAME_RE.match(ln[4] or ""))
                if is_caps:
                    caps_run.append(ln)
                    if len(caps_run) >= 2:
                        y_cut = (caps_run[0][1] + caps_run[0][3]) / 2.0
                        cut_reason = "caps"
                        break
                else:
                    caps_run = []

        if self.debug:
            self._log(
                f"Page {ctx.page_index}: 2-columns @ x={split_x:.1f} "
                f"(tail={'yes' if have_tail_zone else 'no'} "
                f"| wide_upper={len(wide_upper_sorted)} L={len(left_sorted)} "
                f"R={len(right_sorted)} tail_single={len(tail_single_sorted)} "
                f"wide_lower={len(wide_lower_sorted)} | y_cut={y_cut} reason={cut_reason})"
            )

        # If we cut for any of the terminal reasons, mark EOD so later pages are dropped
        if cut_reason in {"proclaim", "signature", "caps", "annex"}:
            self.terminal_reached = True

        # 9) unified emission is built below (pre-emission removed)
        if cut_reason in {"proclaim", "signature", "caps", "annex"}:
            self.terminal_reached = True

        # ---- UNIFIED EMISSION (apply cut to ALL buckets, drop ANNEX heading line) ----

        def _keep_above_and_not_annex(lines_sorted: list[Line], cut: float | None) -> list[Line]:
            """Keep only lines above the cut.
            Also drop the ANNEX heading itself and proclamation lines.
            """
            out: list[Line] = []
            for ln in lines_sorted:
                txt = ln[4] if isinstance(ln[4], str) else ""
                # drop the ANNEX heading line itself
                if _is_annex_heading_line(txt):
                    continue
                if cut is None:
                    out.append(ln)
                    continue
                y_mid = (ln[1] + ln[3]) / 2.0
                # Keep items visually ABOVE the cut; also drop proclamation lines
                if y_mid > cut and not PROCLAIM_RE.match(txt):
                    out.append(ln)
            return out

        # Apply to all buckets
        wide_upper_emit = _keep_above_and_not_annex(wide_upper_sorted, y_cut)
        left_emit = _keep_above_and_not_annex(left_sorted, y_cut)
        right_emit = _keep_above_and_not_annex(right_sorted, y_cut)
        tail_single_emit = _keep_above_and_not_annex(tail_single_sorted, y_cut)
        wide_lower_emit = _keep_above_and_not_annex(wide_lower_sorted, y_cut)

        out_parts: list[str] = []

        def _safe_text(lines: list[Line]) -> str:
            s = _lines_to_text(lines)
            # Guard: _lines_to_text always returns a string, but be defensive
            return s if isinstance(s, str) else ""

        if wide_upper_emit:
            out_parts.append(_safe_text(wide_upper_emit))
        if left_emit:
            if out_parts:
                out_parts.append("")
            out_parts.append(_safe_text(left_emit))
        if right_emit:
            if out_parts:
                out_parts.append("")
            out_parts.append(_safe_text(right_emit))
        if tail_single_emit:
            if out_parts:
                out_parts.append("")
            out_parts.append(_safe_text(tail_single_emit))
        if wide_lower_emit:
            if out_parts:
                out_parts.append("")
            out_parts.append(_safe_text(wide_lower_emit))

        # EXTRA guard against accidental None in parts
        out_parts = [p if isinstance(p, str) else "" for p in out_parts]
        page_text = "\n".join(out_parts).rstrip()

        # remember split for next page
        self.prev_split_x = split_x
        self.prev_w = w
        return page_text


# --------------------------- Text joiner ----------------------------------- #


def _lines_to_text(lines: list[Line]) -> str:
    """
    Group nearby lines into paragraphs, join with newlines,
    and de-hyphenate simple word breaks (prev endswith '-' + next starts with Greek lowercase).
    Always returns a string; sanitizes any non-str text payloads.
    """
    if not lines:
        return ""

    def _s(txt: object) -> str:
        if isinstance(txt, str):
            return txt
        if txt is None:
            return ""
        return str(txt)

    paras: list[list[str]] = []
    curr: list[str] = []
    last_y0: float | None = None
    last_y1: float | None = None

    def flush() -> None:
        if curr:
            paras.append(curr.copy())
            curr.clear()

    for _x0, y0, _x1, y1, t in lines:
        s = _s(t)
        if last_y0 is None:
            curr.append(s)
            last_y0, last_y1 = y0, y1
            continue

        # mypy guard: last_y0/last_y1 are Optional by type; at this point they are set.
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
    # Everything in paras is str now
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
        last_num = last.group(1)
        start = last.start()
        block = full_text[start:].strip()

        print(f"[pdf] LAST ARTICLE = {last_num}")
        print("[pdf] --- LAST ARTICLE BLOCK ---")
        print(block)
        print("[pdf] --- END BLOCK ---\n")

        # Helpful: check if an ANNEX heading still survives in this tail
        try:
            has_annex = bool(ANNEX_HEADING_RE.search(block))
        except NameError:
            has_annex = "ΠΑΡΑΡΤΗΜΑ" in block
        print("[pdf] Contains ANNEX heading?", has_annex)

        # Also dump to file in case stdout is swallowed by the runner
        with open("last_article_debug.txt", "w", encoding="utf-8") as f:
            f.write(block)
    except Exception as e:
        print("[pdf] Debug print of last article failed:", e)


# --------------------------- Public API ----------------------------------- #


def extract_text_whole(path: _PathLike, debug: bool = False) -> str:
    """
    Iterate pages with ColumnExtractor, stop if a terminal anchor is hit,
    then (when debug=True) print/dump the last-article block for inspection.
    """
    extractor = ColumnExtractor(debug=debug)
    out_pages: list[str] = []

    for page_index, layout in enumerate(extract_pages(_to_str_path(path))):
        if not isinstance(layout, LTPage):
            continue

        w, h = layout.width, layout.height
        rot = getattr(layout, "rotate", 0) or 0
        if rot % 180 != 0 and debug:
            print(f"[pdf] Page {page_index}: rotation={rot}° (split may be skipped)")

        lines = list(_iter_lines(layout))
        if not lines:
            out_pages.append("")
            continue

        ctx = PageContext(page_index=page_index, width=w, height=h, rotation=rot)
        page_text = extractor.process_page(ctx, lines)
        out_pages.append(page_text)

        # Stop and drop remaining pages if terminal anchor detected on this page
        if extractor.terminal_reached:
            if debug:
                print(f"[pdf] Stop after page {page_index}: terminal anchor detected.")
            break

    # Build the final text AFTER the loop so we can debug-print it
    full_text = "\n\n".join(out_pages).rstrip()

    # Debug: show the last article block and also write it to a file
    if debug:
        _debug_print_last_article(full_text)

    return full_text


def extract_pdf_text(path: _PathLike, debug: bool = False) -> str:
    return extract_text_whole(path, debug=debug)


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
