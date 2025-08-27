# src/fek_extractor/core.py
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import SCHEMA_VERSION
from .io.pdf import extract_text_whole, iter_lines_from_pdf
from .parsing.articles import Article, build_articles
from .parsing.authority import find_issuing_authorities
from .parsing.headers import find_fek_header_line, parse_fek_header
from .parsing.normalize import dehyphenate_text
from .parsing.rules import parse_text
from .parsing.signatures import find_signatories
from .parsing.subject import extract_subject
from .utils.dates import parse_date_to_iso


def _article_full_sort_key(a: Article) -> tuple[int, int]:
    """Sort full article entries by number, then by start_line."""
    return (a["number"], a["start_line"])


# ----------------------------
# Folding / normalization helpers
# ----------------------------


def _fold(s: str) -> str:
    """Lowercase + strip diacritics (accent-insensitive compare)."""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# ----------------------------
# Context (Part/Title/Chapter) helpers
# ----------------------------

_PART_RE = re.compile(r"(?i)^\s*ΜΕΡΟΣ\s+([Α-Ω])\s*(?:[.:–—-]?\s*(.*))?$")
_TITLE_RE = re.compile(r"(?i)^\s*ΤΙΤΛΟΣ\s+([Α-Ω])\s*(?:[.:–—-]?\s*(.*))?$")
_CHAPTER_RE = re.compile(r"(?i)^\s*ΚΕΦΑΛΑΙΟ\s+([Α-Ω])\s*(?:[.:–—-]?\s*(.*))?$")
_ARTICLE_HEADING_ONLY_RE = re.compile(r"(?i)^\s*[ΆΑ]ρθρο\s+\d+\s*$")


def _sanitize_heading_title(s: str | None) -> str | None:
    """Drop meaningless titles like a bare prime mark."""
    if not s:
        return None
    t = s.strip()
    if not t:
        return None
    if not re.search(r"[A-Za-zΑ-Ωα-ω]", t):
        return None
    return t


def _find_heading_above(
    lines: list[str],
    start_line: int,
    rx: re.Pattern[str],
    scan_back: int = 60,
) -> tuple[str | None, str | None]:
    """
    Scan up to `scan_back` lines above `start_line` and return (letter, title)
    if a heading is found; otherwise (None, None). Robust to out-of-range.
    """
    n = len(lines)
    if n == 0:
        return (None, None)
    try:
        idx = int(start_line) - 1
    except (TypeError, ValueError):
        idx = n - 1
    i = min(max(0, idx), n - 1)
    limit = max(0, i - scan_back)
    while i >= limit:
        raw = lines[i].strip()
        if raw:
            m = rx.match(raw)
            if m:
                letter = m.group(1).strip() if m.group(1) else None
                title = None
                if len(m.groups()) >= 2 and m.group(2):
                    title = m.group(2).strip()
                return (letter, _sanitize_heading_title(title))
        i -= 1
    return (None, None)


def _make_article_display_title(num: int, title: str) -> str:
    """
    Combine article number with a meaningful title; if the title looks like just
    'Άρθρο N', return 'Άρθρο N' without suffix.
    """
    base = f"Άρθρο {num}"
    if not title or _ARTICLE_HEADING_ONLY_RE.match(title):
        return base
    return f"{base}: {title}"


# ----------------------------
# Body -> HTML (UL/LI) renderer
# ----------------------------

_TOP_ITEM_RX = re.compile(r"^(\d+)[\.\)]\s+(.*)$")
_SUB_ITEM_RX = re.compile(
    r"""^(
            \(?[α-ω]\)        |   # α) optionally in parentheses
            [a-z]\)           |   # a)
            [α-ω]\.           |   # α.
            [\-–—•]               # bullets: -, – , —, •
        )\s+(.*)$""",
    re.IGNORECASE | re.VERBOSE,
)


def _drop_redundant_leading_title(body: str, art_title: str) -> str:
    """
    If the first non-empty line of the body is essentially the same as the
    article title, drop it (avoid duplicating the heading inside HTML).
    """
    if not art_title:
        return body
    want = _fold(art_title.strip())
    if not want:
        return body
    lines = body.splitlines()
    for i, ln in enumerate(lines):
        t = ln.strip()
        if not t:
            continue
        if _fold(t) == want:
            return "\n".join(lines[:i] + lines[i + 1 :])
        break
    return body


def _render_body_html(body: str, article_title: str = "") -> str:
    """
    Render article body as nested UL/LI when numbered/bulleted lists are detected.
    Fallback to simple paragraphs if no list markers are present.
    """
    if article_title:
        body = _drop_redundant_leading_title(body, article_title)
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return ""
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_sub: dict[str, Any] | None = None
    saw_top = False
    for ln in lines:
        m_top = _TOP_ITEM_RX.match(ln)
        if m_top:
            saw_top = True
            current_sub = None
            current = {"text": m_top.group(2).strip(), "subs": []}
            items.append(current)
            continue
        m_sub = _SUB_ITEM_RX.match(ln)
        if m_sub and current is not None:
            current_sub = {"text": m_sub.group(2).strip(), "subs": []}
            current["subs"].append(current_sub)
            continue
        if current_sub is not None:
            current_sub["text"] += " " + ln
        elif current is not None:
            current["text"] += " " + ln
    if saw_top and items:

        def render_items(nodes: list[dict[str, Any]]) -> str:
            out: list[str] = ["<ul>"]
            for it in nodes:
                out.append("<li>")
                out.append(html.escape(it["text"]))
                if it["subs"]:
                    out.append(render_items(it["subs"]))
                out.append("</li>")
            out.append("</ul>")
            return "".join(out)

        return render_items(items)
    parts = [f"<p>{html.escape(t)}</p>" for t in lines]
    return "".join(parts)


# ----------------------------
# Infer title from body when missing
# ----------------------------

_ARTICLE_PREFIX_RE = re.compile(r"(?i)^\s*[ΆΑ]ρθρο\s+(\d+)\s*[:.\-–—]?\s*")


def _clean_article_prefix(text: str, num: int) -> str:
    """Strip 'Άρθρο N:' prefix if it exists in the body heading."""

    def repl(m: re.Match[str]) -> str:
        try:
            return "" if int(m.group(1)) == num else m.group(0)
        except Exception:
            return m.group(0)

    s = _ARTICLE_PREFIX_RE.sub(repl, text)
    return re.sub(r"\s+", " ", s).strip()


def _infer_article_title_from_body(body: str, num: int) -> str:
    """
    Use the first non-empty lines *before* the first list item
    (1., 1), α), -, •) as the article's display title.
    """
    if not body:
        return ""
    lines = [ln.strip() for ln in body.splitlines()]
    head: list[str] = []
    for ln in lines:
        if not ln:
            if head:
                break
            continue
        if _TOP_ITEM_RX.match(ln) or _SUB_ITEM_RX.match(ln):
            break
        head.append(ln)
        if len(head) >= 2:
            break
    if not head:
        return ""
    title_raw = " ".join(head)
    title_raw = _clean_article_prefix(title_raw, num)
    if not title_raw or _ARTICLE_HEADING_ONLY_RE.match(title_raw):
        return ""
    return re.sub(r"\s+", " ", title_raw).strip()[:120]


# ----------------------------
# Choose the best article occurrence
# ----------------------------


def _best_articles_by_number(arts: list[Article]) -> dict[int, Article]:
    """
    For each article number, keep the best occurrence:
      1) Max body length wins (real article vs TOC/inline)
      2) Tie-breaker: later start_line
    """
    best: dict[int, Article] = {}
    score: dict[int, tuple[int, int]] = {}  # (body_len, start_line)
    for a in arts:
        num = a["number"]
        body = (a.get("body") or "").strip()
        body_len = len(body)
        start = a.get("start_line", 0)
        if num not in best:
            best[num] = a
            score[num] = (body_len, start)
            continue
        cur_len, cur_start = score[num]
        if body_len > cur_len or (body_len == cur_len and start > cur_start):
            best[num] = a
            score[num] = (body_len, start)
    return best


# ----------------------------
# Main extractor
# ----------------------------


def extract_pdf_info(
    pdf_path: Path,
    patterns: list[str] | None = None,
    dehyphenate: bool = True,
) -> dict[str, Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    # Raw text (full-document)
    raw_text = extract_text_whole(pdf_path)

    # Count pages from the original text (form-feeds intact)
    pages = raw_text.count("\f") + 1 if raw_text else 0

    # Optional dehyphenation
    if dehyphenate:
        raw_text = dehyphenate_text(raw_text)

    # Parse generic metrics + FEK-specific fields from text
    parsed = parse_text(raw_text, patterns=patterns)

    # Per-line view (layout-aware) for headers/signatures and preview
    lines = iter_lines_from_pdf(pdf_path)

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "path": str(pdf_path),
        "filename": pdf_path.name,
        "pages": pages,
        **parsed,
        "first_5_lines": lines[:5],
    }

    # Enrich FEK fields from header lines
    header_line = find_fek_header_line(lines)
    if header_line:
        hdr = parse_fek_header(header_line)
        for k in ("fek_series", "fek_number", "fek_date"):
            if hdr.get(k) and not record.get(k):
                record[k] = hdr[k]
        if (
            record.get("fek_date")
            and not record.get("fek_date_iso")
            and (iso := parse_date_to_iso(record["fek_date"]))
        ):
            record["fek_date_iso"] = iso

    # Subject (ΘΕΜΑ)
    if not record.get("subject"):
        subj = extract_subject(lines)
        if subj:
            record["subject"] = subj

    # Issuing authority
    authorities = find_issuing_authorities(lines)
    if authorities:
        record["issuing_authorities"] = authorities
        record["issuing_authority"] = authorities[0]

    # Build full articles, pick best per number
    articles_full: list[Article] = build_articles(raw_text)
    articles_full_sorted = sorted(articles_full, key=_article_full_sort_key)
    best_by_num = _best_articles_by_number(articles_full_sorted)

    # Assemble dict-shaped "articles"
    articles_map: dict[str, dict[str, str | None]] = {}
    for num, art in sorted(best_by_num.items(), key=lambda kv: kv[0]):
        given_title = (art.get("title") or "").strip()
        body = art.get("body") or ""

        # Fallback from body if parser title is empty/generic
        if not given_title or _ARTICLE_HEADING_ONLY_RE.match(given_title):
            inferred = _infer_article_title_from_body(body, num)
            atitle = inferred or given_title
        else:
            atitle = given_title

        display_title = _make_article_display_title(num, atitle)
        html_body = _render_body_html(body, article_title=atitle)

        start_line = art.get("start_line", 0)
        part_letter, part_title = _find_heading_above(lines, start_line, _PART_RE)
        ttl_letter, ttl_title = _find_heading_above(lines, start_line, _TITLE_RE)
        ch_letter, ch_title = _find_heading_above(lines, start_line, _CHAPTER_RE)

        articles_map[str(num)] = {
            "title": display_title,
            "html": html_body,
            "part_letter": part_letter,
            "part_title": part_title,
            "title_letter": ttl_letter,
            "title_title": ttl_title,
            "chapter_letter": ch_letter,
            "chapter_title": ch_title,
        }

    record["articles"] = articles_map
    record["articles_count"] = len(articles_map)

    # Signatories
    record["signatories"] = find_signatories(lines, tail_scan=200)

    return record
