# src/fek_extractor/parsing/html_blocks.py
from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["iter_block_texts", "strip_leading_block_with_text"]

# First blocks we care about: <p>...</p>, <h1-3>...</hN>, <li>...</li>
_BLOCK_RE = re.compile(
    r"\s*(<p>.*?</p>|<h[1-3]>.*?</h[1-3]>|<li>.*?</li>)",
    flags=re.IGNORECASE | re.DOTALL,
)

# Strip tags to recover plain text inside a single block
_PLAIN_TEXT_RE = re.compile(r"<[^>]+>")


def iter_block_texts(html: str, limit: int = 6) -> Iterable[str]:
    """
    Yield plain-text content of the first N HTML blocks in order.
    Blocks considered: <p>, <h1-3>, <li>.
    """
    count = 0
    for m in _BLOCK_RE.finditer(html or ""):
        if count >= limit:
            break
        blk = m.group(1)
        txt = _PLAIN_TEXT_RE.sub("", blk).strip()
        if txt:
            yield txt
            count += 1


def strip_leading_block_with_text(html: str, text: str) -> str:
    """
    If the first block's plain text equals `text` (case/space-insensitive),
    remove that block and return the remainder. Otherwise return `html` unchanged.
    """
    if not html or not text:
        return html
    want = re.sub(r"\s+", " ", text.strip()).lower()

    for m in _BLOCK_RE.finditer(html):
        blk = m.group(1)
        raw = _PLAIN_TEXT_RE.sub("", blk)
        got = re.sub(r"\s+", " ", raw.strip()).lower()
        if got == want:
            start, end = m.span(1)
            return html[:start] + html[end:]
        break  # only consider the first block
    return html
