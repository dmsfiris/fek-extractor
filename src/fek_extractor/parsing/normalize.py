from __future__ import annotations

import html as htmlmod
import re
import unicodedata
from collections.abc import Iterable

# collapse runs of whitespace incl. non-breaking space
_WHITESPACE_RE = re.compile(r"[\s\u00A0]+", re.UNICODE)

# hyphen-like characters that often appear at end-of-line
_HYPHENS = {"-", "‐", "–"}  # ASCII hyphen, hyphen, non-breaking hyphen, en-dash
_SOFT_HYPHEN = "\u00ad"  # discretionary soft hyphen


def normalize_text(s: str) -> str:
    """Unescape HTML, normalize Unicode NFC, drop soft hyphens, collapse whitespace."""
    s = htmlmod.unescape(s)
    s = s.replace("\u00a0", " ")  # NBSP -> space
    s = s.replace(_SOFT_HYPHEN, "")  # remove discretionary hyphen
    s = unicodedata.normalize("NFC", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s


def fix_soft_hyphens_inline(s: str) -> str:
    """Remove discretionary soft hyphens (U+00AD) but leave normal hyphens intact."""
    return s.replace(_SOFT_HYPHEN, "")


def _ends_with_hyphen(line: str) -> bool:
    line = line.rstrip()
    return bool(line) and line[-1] in _HYPHENS


def _starts_with_lower_alpha(s: str) -> bool:
    """True if first non-space char is a lowercase letter (Greek or Latin)."""
    s = s.lstrip()
    if not s:
        return False
    c = s[0]
    # .isalpha() works for Greek; compare to lowercase to check case
    return c.isalpha() and c == c.lower()


def dehyphenate_lines(lines: Iterable[str]) -> list[str]:
    """Join soft-wrapped hyphenated words across *lines*.

    If a line ends with a hyphen-like char and the next line starts with a lowercase letter,
    drop the hyphen and concatenate without an extra space.
    """
    out: list[str] = []
    for line in lines:
        if out and _ends_with_hyphen(out[-1]) and _starts_with_lower_alpha(line):
            prev = out.pop().rstrip()
            # remove just the final hyphen char
            merged = prev[:-1] + line.lstrip()
            out.append(merged)
        else:
            out.append(line)
    return out


def dehyphenate_text(text: str) -> str:
    """Apply dehyphenation to a multi-line string and return a multi-line string."""
    return "\n".join(dehyphenate_lines(text.splitlines()))
