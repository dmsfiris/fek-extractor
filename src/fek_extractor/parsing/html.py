# src/fek_extractor/parsing/html.py
from __future__ import annotations

import re

from ..utils.html_cleanup import tidy_article_html
from .heuristics import prev_ends_connector
from .normalize import dehyphenate_lines, fix_soft_hyphens_inline

__all__ = ["lines_to_html"]

# -----------------------------
# Bullet detection (strict)
# -----------------------------

_BULLET_DASH_RE = re.compile(r"^\s*[-•]\s+(?P<text>.+)$")
# Numeric bullets like "2)" or "2." — but NOT "(2)"
_BULLET_NUM_RE = re.compile(r"^\s*(?P<num>\d{1,2})[.)]\s+(?P<text>.+)$")
_BULLET_ROMAN_RE = re.compile(r"^\s*\(?(?P<rn>[ivxIVX]+)[.)]\s+(?P<text>.+)$")

# Greek alpha-numeric bullets: accept *only* (α)  or  α)  or  α.
# (Prevents false positives like "Η Εταιρεία ..." turning into a bullet.)
_BULLET_GREEK_RE = re.compile(r"^\s*(?:\((?P<gr>[α-ω])\)|(?P<gr2>[α-ω])[.)])\s+(?P<text>.+)$")

_HEADING_LIKE_RE = re.compile(
    r"^\s*(?:ΜΕΡΟΣ|ΤΙΤΛΟΣ|ΚΕΦΑΛΑΙΟ|ΤΜΗΜΑ|ΠΑΡΑΡΤΗΜΑ|ΑΡΘΡΟ|Άρθρο)\b",
    re.UNICODE | re.IGNORECASE,
)

_STRONG_STOP_RE = re.compile(r"[.!;:·…»)]\s*$", re.UNICODE)


def _parse_bullet(line: str) -> tuple[str, str] | None:
    """
    Return (kind, text) if line is a bullet.
    Kinds: 'dash', 'num', 'roman', 'greek'.
    """
    m = _BULLET_DASH_RE.match(line)
    if m:
        return "dash", m.group("text").strip()

    m = _BULLET_NUM_RE.match(line)
    if m:
        return "num", m.group("text").strip()

    m = _BULLET_ROMAN_RE.match(line)
    if m:
        return "roman", m.group("text").strip()

    m = _BULLET_GREEK_RE.match(line)
    if m:
        # Either group 'gr' or 'gr2' will exist; we only need the text
        return "greek", m.group("text").strip()

    return None


def _ends_with_colon(s: str) -> bool:
    return (s or "").rstrip().endswith(":")


# -----------------------------
# Continuation heuristics
# -----------------------------
# A plain line looks like continuation of the previous <li> if it starts with:
#   - lowercase (el/en), or
#   - punctuation, or
#   - an opening parenthesis.
_LOWER_START_RE = re.compile(r"^[a-zα-ωά-ώ]")
_PUNCT_START_RE = re.compile(r"^[,.;:·)»]")
_PAREN_START_RE = re.compile(r"^\(")
_NUMERIC_CONT_START_RE = re.compile(r"^\d{1,4}\b(?!\s*[.)])", re.UNICODE)


def _looks_like_li_continuation(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    if _PUNCT_START_RE.match(t):
        return True
    if _PAREN_START_RE.match(t):
        return True
    # NEW: numeric tail like "977 του Κ.Πολ.Δ." (but not "1.", "1)")
    if _NUMERIC_CONT_START_RE.match(t):
        return True
    return bool(_LOWER_START_RE.match(t))


# -----------------------------
# ULTrees (recursive lists)
# -----------------------------


class _Item:
    __slots__ = ("text", "children")

    def __init__(self, text: str) -> None:
        self.text: str = text
        self.children: list[_Item] = []


class _ULTree:
    """
    A list block with nested items. We keep a stack of levels (each a list of
    _Item) and a parallel stack of marker kinds for 'different-type → new top UL'.
    """

    def __init__(self, root_kind: str) -> None:
        self.levels: list[list[_Item]] = [[]]
        self.kinds: list[str] = [root_kind]

    @property
    def cur_items(self) -> list[_Item]:
        return self.levels[-1]

    @property
    def cur_kind(self) -> str:
        return self.kinds[-1]

    def last_item(self) -> _Item | None:
        return self.cur_items[-1] if self.cur_items else None

    def push_child_level(self, child_kind: str) -> None:
        parent = self.last_item()
        if parent is None:
            return
        parent.children = parent.children or []
        self.levels.append(parent.children)
        self.kinds.append(child_kind)

    def pop_level(self) -> None:
        if len(self.levels) > 1:
            self.levels.pop()
            self.kinds.pop()

    def add_item(self, text: str) -> None:
        self.cur_items.append(_Item(text))

    def append_to_last(self, extra_text: str) -> None:
        last = self.last_item()
        if last is None:
            return
        last.text = (last.text + " " + extra_text.strip()).strip()

    def render(self) -> str:
        def _render_items(items: list[_Item]) -> str:
            out: list[str] = []
            for it in items:
                if it.children:
                    out.append(
                        "<li>" + it.text + "<ul>" + _render_items(it.children) + "</ul>" + "</li>"
                    )
                else:
                    out.append("<li>" + it.text + "</li>")
            return "".join(out)

        return "<ul>" + _render_items(self.levels[0]) + "</ul>"


def _nest_paragraph_between_uls_into_prev_li(html: str) -> str:
    """
    Turn:
      …<li>…</li></ul><p>P_TEXT</p><ul>…
    into:
      …<li>…<p>P_TEXT</p></li></ul><ul>…
    (so the paragraph becomes part of the previous <li>)
    Run BEFORE coalescing </ul><ul>.
    """
    # Match the last <li> of a UL, then a <p>, then the start of next UL.
    # Non-greedy '.*?' keeps content local to that final LI.
    pat: re.Pattern[str] = re.compile(
        r"(?is)(<li\b[^>]*>.*?)(</li>\s*</ul>)" r"\s*<p>(.*?)</p>\s*(?=<ul\b)"
    )
    prev = None
    while prev != html:
        prev = html
        html = pat.sub(lambda m: f"{m.group(1)}{(m.group(3) or '').strip()}{m.group(2)}", html)
    return html


def _merge_soft_paragraph_breaks(html: str) -> str:
    """
    Merge mid-sentence </p><p> only when:
      - left paragraph does NOT end with strong punctuation, and
      - right paragraph looks like a continuation,
      - and neither side is a heading per _HEADING_LIKE_RE.
    """
    pat: re.Pattern[str] = re.compile(r"(?is)<p>(.*?)</p>\s*<p>(.*?)</p>")

    def repl(m: re.Match[str]) -> str:
        a = (m.group(1) or "").strip()
        b = (m.group(2) or "").strip()
        if not a or not b:
            return m.group(0)

        # use your existing heading detector
        if _HEADING_LIKE_RE.match(a) or _HEADING_LIKE_RE.match(b):
            return m.group(0)

        if not _STRONG_STOP_RE.search(a) and _looks_like_li_continuation(b):
            return f"<p>{a} {b}</p>"
        return m.group(0)

    prev: str | None = None
    while prev != html:
        prev = html
        html = pat.sub(repl, html)
    return html


# -----------------------------
# Public API
# -----------------------------


def lines_to_html(lines: list[str]) -> str:
    """
    Render lines to HTML safely:
      - Inline normalize: fix_soft_hyphens_inline.
      - Cross-line: dehyphenate_lines (NO text-only interleaving; geometry
        handling happens upstream in pdf.py).
      - Build nested ULs using 'ends-with-colon' → child UL rule.
      - If a non-bullet line looks like a continuation and a list is open,
        append to the last <li>.
      - Consecutive non-bullet lines merge into a paragraph; a blank line flushes.
      - Post-pass: coalesce adjacent <ul> blocks.
      - Tidy with tidy_article_html.
    """
    # 1) Inline soft-hyphen cleanup (keeps visible hyphens intact).
    lines = [fix_soft_hyphens_inline(ln) for ln in lines]

    # 2) Safe cross-line dehyphenation across the list — geometry-aware splicing
    #    (e.g., cross-column continuations) is handled earlier in pdf/core.
    lines = dehyphenate_lines(lines)

    blocks: list[str] = []
    current_list: _ULTree | None = None
    current_paragraph: str | None = None

    def flush_paragraph() -> None:
        nonlocal current_paragraph
        if current_paragraph:
            blocks.append("<p>" + current_paragraph.strip() + "</p>")
            current_paragraph = None

    def flush_list() -> None:
        nonlocal current_list
        if current_list is not None:
            blocks.append(current_list.render())
            current_list = None

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        i += 1
        s = (raw or "").strip()
        if not s:
            # blank line: end paragraph
            flush_paragraph()
            continue

        parsed = _parse_bullet(s)
        if parsed:
            # new bullet item — close any paragraph first
            flush_paragraph()
            kind, text = parsed

            if current_list is None:
                current_list = _ULTree(kind)
                current_list.add_item(text)
                continue

            last = current_list.last_item()
            # Descend into a child list if the parent ends with a colon
            if last and _ends_with_colon(last.text):
                current_list.push_child_level(kind)
                current_list.add_item(text)
                continue

            # If marker kind changed inside nested lists, pop until compatible
            while len(current_list.kinds) > 1 and kind not in current_list.kinds:
                current_list.pop_level()

            if kind == current_list.cur_kind:
                current_list.add_item(text)
            else:
                # At top level with a new marker kind: flush and start a new list
                if len(current_list.kinds) == 1:
                    flush_list()
                    current_list = _ULTree(kind)
                    current_list.add_item(text)
                else:
                    # Not at top level: pop until kinds match, then add
                    while current_list.cur_kind != kind and len(current_list.kinds) > 1:
                        current_list.pop_level()
                    current_list.add_item(text)
            continue

        # Non-bullet line
        if current_list is not None:
            last = current_list.last_item()
            # 1) classic continuation (lowercase/punct/paren/numeric tail)
            if _looks_like_li_continuation(s):
                current_list.append_to_last(s)
                continue
            # 2) generic continuation gated by language heuristic
            if last and prev_ends_connector(last.text) and not _HEADING_LIKE_RE.match(s):
                current_list.append_to_last(s)
                continue
            # 3) otherwise: NOT a continuation → close the list, keep this as paragraph
            flush_list()
            if current_paragraph is None:
                current_paragraph = s
            else:
                current_paragraph += " " + s
            continue  # important: we've handled this line

        # Plain paragraph text
        flush_list()
        if current_paragraph is None:
            current_paragraph = s
        else:
            current_paragraph += " " + s

    # Flush any trailing constructs
    flush_paragraph()
    flush_list()

    html = "".join(blocks)

    html = _merge_soft_paragraph_breaks(html)

    # NEW: keep 'Υπάγεται …' as a paragraph but inside the last <li>
    html = _nest_paragraph_between_uls_into_prev_li(html)

    # Coalesce adjacent <ul> blocks created by blank lines between list chunks
    # (Avoids <ul>..</ul><ul>..</ul> when logically one list)
    html = re.sub(r"</ul>\s*<ul>", "", html)

    return tidy_article_html(html)
