# src/fek_extractor/parsing/normalize.py
from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable

# ----------------------------
# Character classes / helpers
# ----------------------------

# Greek + Latin lowercase ranges we care about for safe joins
_GREEK_LOWER = "α-ωάέήίόύώϊΐϋΰς"
_LATIN_LOWER = "a-z"
_LOWER = _LATIN_LOWER + _GREEK_LOWER

# Hyphen-like characters commonly seen in PDFs:
# ASCII hyphen, SOFT HYPHEN, HYPHEN, NON-BREAKING HYPHEN,
# FIGURE DASH, EN DASH, EM DASH, MINUS SIGN
_HYPHENS = r"\-\u00AD\u2010\u2011\u2012\u2013\u2014\u2212"

# Regex helpers compiled once
_RX_LOWER = rf"[{_LOWER}]"
_RX_LAST_TOKEN_BEFORE_DASH = re.compile(
    rf"([{_LOWER}]+)\s*[-\u00AD\u2010\u2011\u2012\u2013\u2014\u2212]$",
    re.UNICODE,
)
_RX_FIRST_TOKEN_AFTER = re.compile(rf"([{_LOWER}]+)(.*)$", re.UNICODE)


# ----------------------------
# Dehyphenation exceptions / protected pairs
# ----------------------------
# If a hyphenated break splits these pairs across lines/spaces,
# we will join them using the provided joiner instead of concatenation.
# (left_regex, right_regex, joiner)
_DEHYPH_EXCEPTIONS_RAW: list[tuple[str, str, str]] = [
    # κράτος-μέλος family
    (
        r"(?:[Κκ]ράτος|[Κκ]ράτους|[Κκ]ράτη|[Κκ]ρατών)",
        r"(?:[Μμ]έλος|[Μμ]έλους|[Μμ]έλη|[Μμ]ελών)",
        "-",
    ),
    # add more pairs here as needed
]
_DEHYPH_EXCEPTIONS = [
    (re.compile(rf"^{L}$"), re.compile(rf"^{R}$"), joiner)
    for (L, R, joiner) in _DEHYPH_EXCEPTIONS_RAW
]


def add_dehyphenation_exception(
    left_variants: Iterable[str], right_variants: Iterable[str], joiner: str = "-"
) -> None:
    """
    Extend protected pairs at runtime:
      add_dehyphenation_exception(["κράτος","κράτους"], ["μέλος","μέλους"])
    """
    L = "|".join(map(re.escape, left_variants))
    R = "|".join(map(re.escape, right_variants))
    _DEHYPH_EXCEPTIONS.append((re.compile(rf"^(?:{L})$"), re.compile(rf"^(?:{R})$"), joiner))


def _exception_joiner(left: str, right: str) -> str | None:
    """Return a custom joiner if (left, right) matches an exception pair."""
    for Lrx, Rrx, joiner in _DEHYPH_EXCEPTIONS:
        if Lrx.match(left) and Rrx.match(right):
            return joiner
    return None


def _normalize_known_compounds(text: str) -> str:
    """
    Normalize known hyphenated compounds anywhere in text, regardless of how
    they appear (glued, spaced, multiple dashes/spaces). Currently handles
    the κράτος-μέλος family and can be extended similarly.
    """
    if not text:
        return text

    # Always hyphen family
    LEFT = r"(?:κράτος|κράτους|κράτη|κρατών)"
    RIGHT = r"(?:μέλος|μέλους|μέλη|μελών)"

    # (a) glued: 'κράτουςμέλους' -> 'κράτους-μέλους'
    text = re.sub(rf"(?i)\b({LEFT})({RIGHT})\b", r"\1-\2", text)

    # Always glued family
    HYPHENS = r"[\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u00AD]"
    LEFT2 = r"(?:ΑΕ)"  # extensible: e.g., r"(?:ΑΕ|ΙΚΕ)"
    RIGHT2 = r"(?:ΠΕΥ)"  # extensible: e.g., r"(?:ΠΕΥ|ΕΠ)"

    # ΑΕ-ΠΕΥ (with any hyphen variant, optional spaces) → ΑΕΠΕΥ
    text = re.sub(
        rf"(?iu)\b({LEFT2})\s*{HYPHENS}\s*({RIGHT2})\b",
        r"\1\2",
        text,
    )

    # (b) any mix of spaces/hyphen-like chars between -> single ASCII hyphen
    text = re.sub(
        rf"(?i)\b({LEFT})\s*(?:[{_HYPHENS}]\s*)+\s*({RIGHT})\b",
        r"\1-\2",
        text,
    )

    # (c) plain spaces only -> hyphen
    text = re.sub(rf"(?i)\b({LEFT})\s+({RIGHT})\b", r"\1-\2", text)

    return text


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
    # Drop any remaining soft hyphens, just in case
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
    # normalize a couple of frequent non-breaking/odd spaces to real space
    s = s.replace("\u00a0", " ")  # NBSP
    s = s.replace("\u202f", " ")  # NNBSP (narrow no-break space)
    s = s.replace("\ufeff", " ")  # ZWNBSP (BOM)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s, flags=re.UNICODE)
    return s.strip()


# Pre-compiled join patterns (performance)
_pat1 = re.compile(  # hyphen + optional spaces + newline + optional spaces
    rf"([{_LOWER}]+)[{_HYPHENS}]\s*\n\s*([{_LOWER}]+)",
    re.UNICODE,
)
_pat2 = re.compile(  # hyphen + spaces (same line)
    rf"([{_LOWER}]+)[{_HYPHENS}]\s+([{_LOWER}]+)",
    re.UNICODE,
)
_pat3 = re.compile(  # spaces around a hyphen-like char (PDF artifacts)
    rf"([{_LOWER}]+)\s+[{_HYPHENS}]\s+([{_LOWER}]+)",
    re.UNICODE,
)


def dehyphenate_text(text: str) -> str:
    """
    Join words broken by hyphenation across line breaks or spaces WITHOUT altering accents.

    Examples fixed:
      'εφαρμόζο-\\nνται'   -> 'εφαρμόζονται'
      'εφαρμόζο-   νται'   -> 'εφαρμόζονται'
      'επο- πτικών'        -> 'εποπτικών'

    We only join when both sides are lowercase letters to avoid
    touching true hyphens like 'ΣΠΥΡΙΔΩΝ - ΑΔΩΝΙΣ'.

    Exception-aware: for configured pairs (e.g., 'κράτους-μέλους') we keep/insert
    the configured joiner instead of concatenating.
    """
    if not text:
        return ""

    # Neutralize inline SOFT HYPHENS first
    text = fix_soft_hyphens_inline(text)

    def _merge(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        j = _exception_joiner(left, right)
        return left + (j if j is not None else "") + right

    # Apply three join forms
    text = _pat1.sub(_merge, text)
    text = _pat2.sub(_merge, text)
    text = _pat3.sub(_merge, text)

    # Normalize well-known hyphen compounds (handles glued/space/multi-dash variants)
    text = _normalize_known_compounds(text)

    return text


def dehyphenate_lines(lines: list[str]) -> list[str]:
    """
    Line-wise variant for pipelines that process text per line.
    If a line ends with a hyphen-like char and the next line starts with a lowercase
    letter, join without adding a space (drop the hyphen). No accent changes.

    Example:
      ["... μεγα-", "λο κείμενο."] -> ["... μεγαλο κείμενο."]

    Exception-aware: for configured pairs (e.g. 'κράτους' + 'μέλους'),
    it inserts the configured joiner (hyphen for κράτος-μέλος).
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
                and cur_r[-1] in "-\u00ad\u2010\u2011\u2012\u2013\u2014\u2212"
                and nxt
                and re.match(_RX_LOWER, nxt, flags=re.UNICODE)
            ):
                m_left = _RX_LAST_TOKEN_BEFORE_DASH.search(cur_r)
                m_right = _RX_FIRST_TOKEN_AFTER.match(nxt)
                if m_left and m_right:
                    left = m_left.group(1)
                    right, rest = m_right.group(1), m_right.group(2)
                    joiner = _exception_joiner(left, right) or ""
                    joined = cur_r[: m_left.start(1)] + left + joiner + right + rest
                    joined = _normalize_known_compounds(joined)
                    out.append(joined)
                    i += 2
                    continue
        out.append(cur)
        i += 1
    return out
