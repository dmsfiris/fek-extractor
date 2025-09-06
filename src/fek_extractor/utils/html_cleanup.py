# src/fek_extractor/utils/html_cleanup.py
"""
HTML cleanup utilities for FEK article bodies.

Goals
-----
1) Merge split list fragments:
   - Collapse consecutive <ul>…</ul><ul>…</ul> (or <ol>) that share the
     same parent.

2) Glue "orphan" paragraphs back to the last bullet:
   - For patterns like: <ul><li>…</li></ul><p>(Α΄ 14).</p>
   - Or when the previous <li> clearly continues (it didn’t end with
     . ; : ·), e.g. a line-break turned into </ul><p>Συμβουλίου…</p>.

Public API
----------
    tidy_article_html(html: str) -> str
"""

from __future__ import annotations

from collections.abc import Iterable

from bs4 import BeautifulSoup
from bs4.element import Comment, NavigableString, PageElement, Tag

__all__ = ["tidy_article_html"]

# Sentence enders for Greek-legal prose
SENTENCE_ENDERS: tuple[str, ...] = (".", ";", ":", "·", "·", "!", "?")
# Closing punctuation/quotes to skip when checking the real last char
CLOSING_TRAILERS: tuple[str, ...] = tuple(")]}»›”’'\"")

HEADING_CUES: tuple[str, ...] = (
    "ΜΕΡΟΣ",
    "ΚΕΦΑΛΑΙΟ",
    "ΤΙΤΛΟΣ",
    "ΆΡΘΡΟ",
    "ΑΡΘΡΟ",  # sometimes all-caps, sometimes titlecased
)


def _first_real_sibling(tag: Tag, direction: str = "prev") -> Tag | None:
    """
    Get the nearest previous/next sibling that is a Tag
    (ignore whitespace strings/comments).
    """
    sib_iter: Iterable[PageElement] = (
        tag.previous_siblings if direction == "prev" else tag.next_siblings
    )
    for sib in sib_iter:
        if isinstance(sib, Tag):
            return sib
        if isinstance(sib, Comment):
            continue
        if isinstance(sib, NavigableString) and str(sib).strip():
            # Non-empty stray text is a blocker
            return None
    return None


def _last_top_level_li(list_tag: Tag) -> Tag | None:
    """
    Get the last top-level <li> child of a <ul>/<ol>
    (not nested inside other <li>).
    """
    if list_tag.name not in ("ul", "ol"):
        return None
    for child in reversed(list_tag.contents):
        if isinstance(child, Tag) and child.name == "li":
            return child
    return None


def _text_of(tag: Tag) -> str:
    return tag.get_text(separator="", strip=True)


def _is_all_caps_heading_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    # Strong heading cues first
    for cue in HEADING_CUES:
        if cue in t.upper():
            return True
    # Very shouty short lines (avoid gluing)
    return bool(len(t) <= 80 and t.isupper())


def _is_short_parenthetical(text: str, max_len: int = 60) -> bool:
    """
    True if text looks like a small parenthetical supplement,
    e.g. "(Α΄ 14)."
    """
    t = text.strip()
    if not t:
        return False
    if len(t) <= max_len and t.startswith(("(", "[")):
        return True
    # Pure parenthetical even if it ends with a period
    return bool(len(t) <= max_len and t.startswith("(") and t.endswith((")", ").")))


def _strip_trailing_closers(text: str) -> tuple[str, str]:
    """
    Remove trailing closing quotes/brackets to inspect the true last
    character, but return both (core, stripped_tail).
    """
    t = text.rstrip()
    tail = ""
    while t and t[-1] in CLOSING_TRAILERS:
        tail = t[-1] + tail
        t = t[:-1].rstrip()
    return t, tail


def _ends_with_sentence_punct(text: str) -> bool:
    """
    True if `text` (ignoring closing quotes/brackets) ends with
    a sentence-terminating punctuation.
    """
    core, _tail = _strip_trailing_closers(text)
    return bool(core) and core[-1] in SENTENCE_ENDERS


def _should_glue_into_last_li(p_tag: Tag, last_li: Tag) -> bool:
    """
    Decide whether <p> should be glued into the last <li> of the previous
    list.
      - If the <p> is a short parenthetical -> glue.
      - Else if the last <li> does NOT end with sentence punctuation ->
        glue (continuation).
      - Avoid gluing if the <p> looks like a heading/section label.
    """
    p_text = _text_of(p_tag)
    if not p_text:
        return False
    if _is_all_caps_heading_like(p_text):
        return False

    li_text = _text_of(last_li)

    if _is_short_parenthetical(p_text):
        return True

    # If previous bullet doesn't end a sentence, this <p> is a continuation.
    return not _ends_with_sentence_punct(li_text)


def _append_with_spacing(target: Tag, source: Tag) -> None:
    """
    Append the contents of `source` into `target`, ensuring reasonable
    spacing.
    """
    target_text = target.get_text()
    src_text = _text_of(source)

    need_space = True
    if not target_text:
        need_space = False
    else:
        trimmed = target_text.rstrip()
        # If already ends with whitespace or an opening bracket/dash,
        # skip extra space
        if trimmed.endswith((" ", "\u00a0", "(", "[", "{", "—", "–", "-")):
            need_space = False
        # If the source starts with a closing punctuation (rare),
        # do NOT prepend space
        first = src_text[:1]
        if first in (")", ",", ".", ";", "·", "·", ":"):
            need_space = False

    if need_space:
        target.append(NavigableString(" "))

    # Move all children of source into target
    for node in list(source.contents):
        target.append(node.extract())


def _merge_adjacent_lists(root: Tag) -> bool:
    """
    Merge consecutive <ul>/<ol> siblings that share the same parent.
    Returns True if any change was made.
    """
    changed = False

    for parent in root.find_all(True):
        # parent is a Tag
        assert isinstance(parent, Tag)
        idx = 0
        while idx < len(parent.contents):
            node_pe: PageElement = parent.contents[idx]
            if not isinstance(node_pe, Tag) or node_pe.name not in ("ul", "ol"):
                idx += 1
                continue

            node = node_pe  # narrowed to Tag
            j = idx + 1
            while j < len(parent.contents):
                nxt_pe: PageElement = parent.contents[j]

                # Skip comments and whitespace-only strings
                if isinstance(nxt_pe, Comment):
                    j += 1
                    continue
                if isinstance(nxt_pe, NavigableString) and not str(nxt_pe).strip():
                    j += 1  # skip whitespace
                    continue

                if isinstance(nxt_pe, Tag) and nxt_pe.name == node.name:
                    # Move all top-level <li> from nxt into node
                    li_children: list[Tag] = [
                        c for c in nxt_pe.contents if isinstance(c, Tag) and c.name == "li"
                    ]
                    if li_children:
                        for li in li_children:
                            node.append(li.extract())
                        changed = True
                    nxt_pe.decompose()
                    # Do not advance j; siblings collapsed into j
                    continue
                break  # not the same-type list next; stop merging

            idx += 1

    return changed


def _glue_orphan_paragraphs(root: Tag) -> bool:
    """
    For any <p> that immediately follows a <ul>/<ol>, glue it into the last
    <li> when it looks like a continuation or a short parenthetical.
    Returns True if any change was made.
    """
    changed = False

    for p in list(root.find_all("p")):
        # p is a Tag (find_all("p") narrows)
        assert isinstance(p, Tag)

        # Skip empty/whitespace-only paragraphs
        if not _text_of(p):
            continue

        prev_tag = _first_real_sibling(p, "prev")
        if not prev_tag or prev_tag.name not in ("ul", "ol"):
            continue

        last_li = _last_top_level_li(prev_tag)
        if not last_li:
            continue

        if _should_glue_into_last_li(p, last_li):
            _append_with_spacing(last_li, p)
            p.decompose()
            changed = True

    return changed


def tidy_article_html(html: str) -> str:
    """
    Normalize FEK article HTML by:
      1) Merging adjacent same-level lists (<ul>/<ol>).
      2) Gluing orphan paragraphs that are continuations/parentheticals
         into the last <li>.
    """
    if not html or not isinstance(html, str):
        return html or ""

    soup = BeautifulSoup(html, "html.parser")

    # Use the body if BS4 wrapped our fragment; else use soup itself
    root_pe: PageElement = soup.body if soup.body else soup
    assert isinstance(root_pe, Tag)
    root: Tag = root_pe

    # Run fixers until stable or max iterations
    for _ in range(4):
        changed = False
        changed |= _merge_adjacent_lists(root)
        changed |= _glue_orphan_paragraphs(root)
        if not changed:
            break

    # Return inner body contents if present; avoid adding <html><body> wrappers
    if soup.body:
        return soup.body.decode_contents()
    return str(soup)
