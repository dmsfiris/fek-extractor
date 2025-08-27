# src/fek_extractor/parsing/normalize.py
from __future__ import annotations

import html
import re
import unicodedata

# ----------------------------
# Character classes / helpers
# ----------------------------

# Greek + Latin lowercase ranges we care about for safe joins
_GREEK_LOWER = "α-ωάέήίόύώϊΐϋΰ"
_LATIN_LOWER = "a-z"
_LOWER = _LATIN_LOWER + _GREEK_LOWER

# Hyphen-like characters commonly seen in PDFs
# ASCII hyphen, soft hyphen, hyphen, non-breaking hyphen
_HYPHENS = r"\-\u00AD\u2010\u2011"


# ----------------------------
# Public API
# ----------------------------


def fix_soft_hyphens_inline(text: str) -> str:
    """
    Remove discretionary/soft hyphens (U+00AD) and join around them when they split words.
    Safe for inline text where soft hyphens should be invisible.
    """
    if not text:
        return ""
    # Join when soft hyphen is surrounded by lowercase letters and optional spaces
    text = re.sub(
        rf"([{_LOWER}])\u00AD\s*([{_LOWER}])",
        r"\1\2",
        text,
        flags=re.UNICODE,
    )
    # Drop any remaining soft hyphens
    return text.replace("\u00ad", "")


def normalize_text(text: str) -> str:
    """
    Light, lossless normalization for parsing:
      - NFC normalize (compose diacritics),
      - convert non-breaking space to space,
      - unescape HTML entities (&amp; → &),
      - collapse runs of whitespace (incl. newlines) to a single space,
      - strip leading/trailing spaces.
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFC", text)
    s = s.replace("\u00a0", " ")  # nbsp → space
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s, flags=re.UNICODE)
    return s.strip()


def dehyphenate_text(text: str) -> str:
    """
    Join words broken by hyphenation across line breaks or spaces WITHOUT altering accents.

    Examples fixed:
      'εφαρμόζο-\\nνται'   -> 'εφαρμόζονται'
      'εφαρμόζο-   νται'   -> 'εφαρμόζονται'
      'επο- πτικών'        -> 'εποπτικών'

    We only join when both sides are lowercase letters to avoid
    touching true hyphens like 'ΣΠΥΡΙΔΩΝ - ΑΔΩΝΙΣ'.
    """
    if not text:
        return ""

    # Neutralize inline soft hyphens first
    text = fix_soft_hyphens_inline(text)

    # 1) Hyphen + optional spaces + newline + optional spaces
    text = re.sub(
        rf"([{_LOWER}]+)[{_HYPHENS}]\s*\n\s*([{_LOWER}])",
        r"\1\2",
        text,
        flags=re.UNICODE,
    )

    # 2) Hyphen + spaces (no newline), common when a linebreak became spaces
    text = re.sub(
        rf"([{_LOWER}]+)[{_HYPHENS}]\s+([{_LOWER}])",
        r"\1\2",
        text,
        flags=re.UNICODE,
    )

    return text


def dehyphenate_lines(lines: list[str]) -> list[str]:
    """
    Line-wise variant used by some pipelines:
    If a line ends with a hyphen-like char and the next line starts with a lowercase
    letter, join without adding a space (drop the hyphen). No accent changes.

    Example:
      ["... μεγα-", "λο κείμενο."] -> ["... μεγαλο κείμενο."]  (accents unchanged)
    """
    if not lines:
        return []

    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if i + 1 < len(lines):
            cur_r = cur.rstrip()
            nxt = lines[i + 1].lstrip()
            if (
                cur_r
                and cur_r[-1] in "-\u00ad\u2010\u2011"
                and nxt
                and re.match(rf"[{_LOWER}]", nxt, flags=re.UNICODE)
            ):
                out.append(cur_r[:-1] + nxt)  # drop the hyphen, concatenate
                i += 2
                continue
        out.append(cur)
        i += 1
    return out
