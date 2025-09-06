# src/fek_extractor/parsing/html.py
from __future__ import annotations

import re

from ..utils.html_cleanup import tidy_article_html
from .normalize import dehyphenate_lines, fix_soft_hyphens_inline

__all__ = ["lines_to_html"]

# -----------------------------
# Bullet detection (strict)
# -----------------------------

_BULLET_DASH_RE = re.compile(r"^\s*[-•]\s+(?P<text>.+)$")
_BULLET_NUM_RE = re.compile(r"^\s*\(?(?P<num>\d{1,2})[.)]\s+(?P<text>.+)$")
_BULLET_ROMAN_RE = re.compile(r"^\s*\(?(?P<rn>[ivxIVX]+)[.)]\s+(?P<text>.+)$")

# Greek alpha-numeric bullets: accept *only* (α)  or  α)  or  α.
# (Prevents false positives like "Η Εταιρεία ..." turning into a bullet.)
_BULLET_GREEK_RE = re.compile(r"^\s*(?:\((?P<gr>[α-ω])\)|(?P<gr2>[α-ω])[.)])\s+(?P<text>.+)$")


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

        if not (raw or "").strip():
            # blank line: end paragraph
            flush_paragraph()
            continue

        parsed = _parse_bullet(raw)
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
        if current_list is not None and _looks_like_li_continuation(raw):
            # append continuation text to the last <li>
            current_list.append_to_last(raw)
            continue

        # Plain paragraph text
        flush_list()
        if current_paragraph is None:
            current_paragraph = raw.strip()
        else:
            current_paragraph += " " + raw.strip()

    # Flush any trailing constructs
    flush_paragraph()
    flush_list()

    html = "".join(blocks)

    # Coalesce adjacent <ul> blocks created by blank lines between list chunks
    # (Avoids <ul>..</ul><ul>..</ul> when logically one list)
    html = re.sub(r"</ul>\s*<ul>", "", html)

    return tidy_article_html(html)
