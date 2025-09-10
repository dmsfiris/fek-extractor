# src/fek_extractor/parsing/articles.py
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Final, Literal, TypedDict

from ..models import Article as ModelArticle
from ..models import Context as Ctx
from .html import lines_to_html
from .rules.shared import (
    balance_subtitle_with_body,
    stitch_article_range_stub_upstream,
)
from .title_fixups import apply_title_body_fixups  # παραμένει για διορθώσεις τίτλων/σώματος

__all__ = [
    "find_articles_in_text",
    "extract_articles",
    "build_articles",
    "build_articles_map",
]

# ---------------------------------------------------------------------
# Regexes (robust to accents/case/letter breaks)
# ---------------------------------------------------------------------

# Include more PDF-ish/zero-width spaces
_WS = r"(?:\s|[\u00A0\u2000-\u200D\u202F\u2060\ufeff])"

# Ά ρ θ ρ ο  (tolerant to letter spacing; now NBSP-aware)
_ARTHRO = rf"(?:[ΑΆA]{_WS}*[ρΡ]{_WS}*[θΘ]{_WS}*[ρΡ]{_WS}*[οΟ])"

ARTICLE_HEADING_RX = re.compile(
    rf"^\s*{_ARTHRO}{_WS}+(?P<num>\d+){_WS}*(?::|[-–—])?{_WS}*(?P<inline>.*)?\s*$",
    re.UNICODE,
)
ARTICLE_START_RX = re.compile(
    rf"^\s*{_ARTHRO}{_WS}+\d+\b",
    re.UNICODE,
)

# allow many prime marks
GREEK_PRIMES: Final[str] = r"[΄'’ʼ′ʹ`´᾽ʹ]?"

# ---- Letter token that prefers multi-character forms over single-letter ----
# Supports:
#   - spelled Greek words: ΠΡΩΤΟ, ΔΕΥΤΕΡΟ, ... (contiguous)
#   - spaced Greek words: Π Ρ Ω Τ Ο (just in case; your _strip_primes removes the spaces)
#   - Roman numerals: IV, VI, ... (contiguous or spaced)
#   - digits: 1, 2, ...
#   - single Greek/Latin letter: Α, B (fallback; primes allowed)
_GREEK_WORD: Final[str] = r"[Ά-ΏΑ-Ω]{2,}"  # e.g., ΠΡΩΤΟ, ΔΕΥΤΕΡΟ
_GREEK_SPACED: Final[str] = r"(?:[Ά-ΏΑ-Ω](?:\s+[Ά-ΏΑ-Ω]){1,})"  # e.g., Π Ρ Ω Τ Ο
_ROMAN: Final[str] = r"[IVXLCDM]+"
_ROMAN_SPACED: Final[str] = r"(?:[IVXLCDM](?:\s+[IVXLCDM]){1,})"
_DIGITS: Final[str] = r"[0-9]+"
_GREEK_SINGLE: Final[str] = r"[Α-ΩA-Z]"

_LETTER_TOKEN: Final[str] = (
    r"(?:"
    + _GREEK_SPACED  # prefer spaced multi-letter first
    + r"|"
    + _GREEK_WORD  # then contiguous multi-letter
    + r"|"
    + _ROMAN_SPACED
    + r"|"
    + _ROMAN
    + r"|"
    + _DIGITS
    + r"|"
    + _GREEK_SINGLE  # single-letter fallback
    + r")(?:\s*"
    + GREEK_PRIMES
    + r")?"
)

# optional separator after the letter (dash/colon/dot/middle dot)
_SEP_OPT: Final[str] = r"(?:[-–—:·.])?"

# ---- Flexible structural headers (one-line; title may be empty) ----
PART_RE = re.compile(
    rf"^\s*ΜΕΡΟΣ{_WS}+(?P<letter>{_LETTER_TOKEN}){_WS}*{_SEP_OPT}" rf"{_WS}*(?P<title>.*)$",
    re.UNICODE,
)
TITLE_RE = re.compile(
    rf"^\s*ΤΙΤΛΟΣ{_WS}+(?P<letter>{_LETTER_TOKEN}){_WS}*{_SEP_OPT}" rf"{_WS}*(?P<title>.*)$",
    re.UNICODE,
)


# ΚΕΦΑΛΑΙΟ with optional spaces; allow Latin only for K/E/A/I/O (NOT Φ/Λ)
_KEFALAIO_WORD = rf"(?:[ΚK]{_WS}*[ΕE]{_WS}*Φ{_WS}*[ΑA]{_WS}*Λ{_WS}*[ΑA]{_WS}*[ΙI]{_WS}*[ΟO])"

CHAPTER_RE = re.compile(
    rf"^\s*{_KEFALAIO_WORD}{_WS}+(?P<letter>{_LETTER_TOKEN}){_WS}*{_SEP_OPT}"
    rf"{_WS}*(?P<title>.*)$",
    re.UNICODE,
)

# NEW: ΤΜΗΜΑ (Section)
SECTION_RE = re.compile(
    rf"^\s*ΤΜΗΜΑ{_WS}+(?P<letter>{_LETTER_TOKEN}){_WS}*{_SEP_OPT}" rf"{_WS}*(?P<title>.*)$",
    re.UNICODE,
)

# Catch headers *anywhere* in a line (even after punctuation without space)
_PART_ANYWHERE_PREFIX = r"(?<![A-Za-zΑ-Ωα-ωΆ-Ώά-ώ])"

PART_ANYWHERE_RE = re.compile(
    rf"{_PART_ANYWHERE_PREFIX}ΜΕΡΟΣ{_WS}+(?:{_LETTER_TOKEN}){_WS}*{_SEP_OPT}" rf"{_WS}*.*$",
    re.UNICODE,
)
TITLE_ANYWHERE_RE = re.compile(
    rf"{_PART_ANYWHERE_PREFIX}ΤΙΤΛΟΣ{_WS}+(?:{_LETTER_TOKEN}){_WS}*{_SEP_OPT}" rf"{_WS}*.*$",
    re.UNICODE,
)
CHAPTER_ANYWHERE_RE = re.compile(
    rf"(?:^|{_PART_ANYWHERE_PREFIX})"  # start of line OR not preceded by a letter
    rf"{_KEFALAIO_WORD}"  # ΚΕΦΑΛΑΙΟ (allowed confusables for K/E/A/I/O)
    rf"{_WS}*(?:{_LETTER_TOKEN})"  # then the chapter letter/word (Δ΄, IV, ΠΡΩΤΟ, etc.)
    rf"{_WS}*{_SEP_OPT}{_WS}*.*$",  # optional separator and the rest of the line
    re.UNICODE,
)
SECTION_ANYWHERE_RE = re.compile(
    rf"{_PART_ANYWHERE_PREFIX}ΤΜΗΜΑ{_WS}+(?:{_LETTER_TOKEN}){_WS}*{_SEP_OPT}" rf"{_WS}*.*$",
    re.UNICODE,
)

INLINE_TITLE_RE = re.compile(
    rf"{_PART_ANYWHERE_PREFIX}ΤΙΤΛΟΣ{_WS}+(?P<letter>{_LETTER_TOKEN}){_WS}*{_SEP_OPT}"
    rf"{_WS}*(?P<title>.*)$",
    re.UNICODE,
)
INLINE_CHAPTER_RE = re.compile(
    rf"(?:^|{_PART_ANYWHERE_PREFIX})"
    rf"{_KEFALAIO_WORD}"
    rf"{_WS}+(?P<letter>{_LETTER_TOKEN}){_WS}*{_SEP_OPT}"
    rf"{_WS}*(?P<title>.*)$",
    re.UNICODE,
)
INLINE_SECTION_RE = re.compile(
    rf"{_PART_ANYWHERE_PREFIX}ΤΜΗΜΑ{_WS}+(?P<letter>{_LETTER_TOKEN}){_WS}*{_SEP_OPT}"
    rf"{_WS}*(?P<title>.*)$",
    re.UNICODE,
)

# Bullets (για να μην τα περνάμε ως τίτλους)
_BULLET_DASH_RE = re.compile(r"^\s*[-•]\s+")
_BULLET_NUM_RE = re.compile(r"^\s*\(?\d{1,2}[.)]\s+")
_BULLET_ROM_RE = re.compile(r"^\s*\(?[ivxIVX]+[.)]\s+")
_BULLET_GR_RE = re.compile(r"^\s*(?:\([α-ω]\)|[α-ω][.)])\s+")


def _is_bullet(s: str) -> bool:
    return any(
        rx.match(s) for rx in (_BULLET_DASH_RE, _BULLET_NUM_RE, _BULLET_ROM_RE, _BULLET_GR_RE)
    )


# --- debug harness ---------------------------------------------------
DEBUG_ENABLE: bool = False  # flip to False to silence all debug
# allow either a concrete article number (int) or the wildcard "*"
DEBUGKey = int | Literal["*"]
DEBUG_ARTICLES: set[DEBUGKey] = {89}  # which article numbers to trace
_DBG_CUR_ARTNO: int | None = None  # set around extraction of each article


def _dbg(*args: object) -> None:
    """Print only when debugging current article."""
    if not DEBUG_ENABLE:
        return
    if _DBG_CUR_ARTNO is None:
        return
    if _DBG_CUR_ARTNO in DEBUG_ARTICLES or "*" in DEBUG_ARTICLES:
        print(*args)


# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------


class _Head(TypedDict):
    idx: int
    num: int
    inline: str | None


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _splitlines_preserve(text: str) -> list[str]:
    return (
        re.sub(r"[\t \u00a0]+$", "", text, flags=re.MULTILINE)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .splitlines()
    )


def _strip_primes(s: str | None) -> str | None:
    if not s:
        return s

    # Extract just the characters from inside the constant's brackets
    prime_chars = GREEK_PRIMES[1:-2]

    # Construct the new pattern
    # It now correctly matches any of the prime characters or a space, one or more times
    return re.sub(f"[{prime_chars}\\s]+", "", s)


def _ctx_to_dict(ctx: Ctx) -> dict[str, Any]:
    return {
        "part_letter": ctx.part_letter,
        "part_title": ctx.part_title,
        "title_letter": ctx.title_letter,
        "title_title": ctx.title_title,
        "chapter_letter": ctx.chapter_letter,
        "chapter_title": ctx.chapter_title,
        # NEW
        "section_letter": ctx.section_letter,
        "section_title": ctx.section_title,
    }


def _dict_to_ctx(d: dict[str, Any] | None) -> Ctx:
    d = d or {}
    return Ctx(
        part_letter=d.get("part_letter"),
        part_title=d.get("part_title"),
        title_letter=d.get("title_letter"),
        title_title=d.get("title_title"),
        chapter_letter=d.get("chapter_letter"),
        chapter_title=d.get("chapter_title"),
        # NEW
        section_letter=d.get("section_letter"),
        section_title=d.get("section_title"),
    )


def _article_model_to_record_dict(m: ModelArticle) -> dict[str, Any]:
    return {
        "title": m.title,
        "html": m.html,
        "part_letter": m.context.part_letter,
        "part_title": m.context.part_title,
        "title_letter": m.context.title_letter,
        "title_title": m.context.title_title,
        "chapter_letter": m.context.chapter_letter,
        "chapter_title": m.context.chapter_title,
        # NEW
        "section_letter": m.context.section_letter,
        "section_title": m.context.section_title,
    }


def _is_toc_like_after(lines: list[str], head_idx: int) -> bool:
    """Heuristic:
    the next non-empty line after 'Άρθρο …' is also 'Άρθρο …'
    (treat as table of contents).
    """
    j = head_idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    return j < len(lines) and ARTICLE_START_RX.match(lines[j]) is not None


def _dedupe_and_skip_toc(heads: list[_Head], lines: list[str]) -> list[_Head]:
    """Keep last occurrence per article number; drop ToC-like stubs
    (matches your working behavior).
    """
    cleaned: list[_Head] = []
    for h in heads:
        if _is_toc_like_after(lines, h["idx"]):
            continue
        cleaned.append(h)

    last_by_num: dict[int, _Head] = {}
    for h in cleaned:
        last_by_num[h["num"]] = h
    return sorted(last_by_num.values(), key=lambda x: x["idx"])


def _find_next_nonempty(lines: list[str], start: int) -> int | None:
    j = start
    while j < len(lines):
        if lines[j].strip():
            return j
        j += 1
    return None


def _is_capital_start(s: str) -> bool:
    return bool(re.match(r"^[A-ZΑ-ΩΆ-Ώ]", s or "", flags=re.UNICODE))


def _extend_header_title(lines: list[str], start: int, max_lines: int = 15) -> tuple[str, int]:
    """
    Συλλογή συνέχειας τίτλου σε επόμενες γραμμές για ΜΕΡΟΣ/ΤΙΤΛΟΣ/ΚΕΦΑΛΑΙΟ/ΤΜΗΜΑ.
    - Μαζεύει έως max_lines γραμμές.
    - Σταματά σε κενή γραμμή, νέο heading, 'Άρθρο …', bullet,
      πολύ μεγάλη γραμμή ή γραμμή που δεν μοιάζει με τμήμα τίτλου.
    Επιστρέφει (joined_text, consumed_lines).
    """
    parts: list[str] = []
    consumed = 0
    j = start

    # Επιτρέπουμε συνέχειες που ξεκινούν με: κεφαλαίο, ή ψηφίο, ή άνοιγμα παρενθέσεων/εισαγωγικών
    _cont_start_ok = re.compile(r'^[A-ZΑ-ΩΆ-Ώ0-9(«"“]')

    while j < len(lines) and consumed < max_lines:
        s = (lines[j] or "").strip()
        if not s:
            break
        # Μην «τρώμε» νέα άρθρα/headers/bullets
        if (
            ARTICLE_START_RX.match(s)
            or PART_RE.match(s)
            or TITLE_RE.match(s)
            or CHAPTER_RE.match(s)
            or SECTION_RE.match(s)
            or _is_bullet(s)
        ):
            break
        # Όριο μήκους για να μη φάμε σώμα
        if len(s) > 240:
            break
        # Γραμμή πρέπει να μοιάζει με κομμάτι τίτλου
        if not _cont_start_ok.match(s):
            break

        parts.append(s)
        consumed += 1
        j += 1

    return (" ".join(parts), consumed)


def _find_structural_header_pos(s: str) -> int | None:
    """
    Return the position in 's' where a structural header starts.
    - 0 when it's at line start (match)
    - index>0 when the header appears mid-line (search)
    - None if not found
    """
    s0 = s or ""
    # start-of-line match?
    m = PART_RE.match(s0) or TITLE_RE.match(s0) or CHAPTER_RE.match(s0) or SECTION_RE.match(s0)
    if m:
        return 0
    # anywhere in the line?
    for rx in (
        PART_ANYWHERE_RE,
        TITLE_ANYWHERE_RE,
        CHAPTER_ANYWHERE_RE,
        SECTION_ANYWHERE_RE,
    ):
        m2 = rx.search(s0)
        if m2:
            return m2.start()
    return None


def _trim_trailing_structural_block(lines: list[str]) -> list[str]:
    """
    Trim the trailing structural block: start from the last structural header
    (ΜΕΡΟΣ/ΤΙΤΛΟΣ/ΚΕΦΑΛΑΙΟ/ΤΜΗΜΑ) and expand *backwards* to the earliest header
    within a small look-back window, ignoring intervening lines.
    If a header is mid-line, keep the text before it.
    """

    # helper reused from your code
    def _find_pos(s: str) -> int | None:
        m = PART_RE.match(s) or TITLE_RE.match(s) or CHAPTER_RE.match(s) or SECTION_RE.match(s)
        if m:
            return 0
        for rx in (
            PART_ANYWHERE_RE,
            TITLE_ANYWHERE_RE,
            CHAPTER_ANYWHERE_RE,
            SECTION_ANYWHERE_RE,
        ):
            m2 = rx.search(s or "")
            if m2:
                return m2.start()
        return None

    # collect all header positions
    indices: list[tuple[int, int]] = []
    for i, s in enumerate(lines):
        pos = _find_pos(s or "")
        if pos is not None:
            indices.append((i, pos))
    if not indices:
        return lines

    # anchor at the last header…
    last_i, last_pos = indices[-1]

    # …and expand backwards to the earliest header in a bounded window
    LOOKBACK = 24  # tune if needed
    cluster_i, cluster_pos = last_i, last_pos
    for i, pos in reversed(indices[:-1]):
        if last_i - i <= LOOKBACK:
            cluster_i, cluster_pos = i, pos
        else:
            break

    # trim from the cluster start; preserve any prefix before an inline header
    prefix = (lines[cluster_i][:cluster_pos] or "").rstrip()
    return (lines[:cluster_i] + [prefix]) if prefix else lines[:cluster_i]


def _split_off_inline_structural(s: str) -> tuple[str, tuple[str, str, str] | None]:
    """
    If s contains an inline TITLE/CHAPTER/SECTION, return (pure_title, (kind, letter, title)).
    Otherwise (s, None).
    """
    s0 = s or ""
    candidates = []
    for kind, rx in (
        ("title", INLINE_TITLE_RE),
        ("chapter", INLINE_CHAPTER_RE),
        ("section", INLINE_SECTION_RE),
    ):
        m = rx.search(s0)
        if m:
            candidates.append((m.start(), kind, m))
    if not candidates:
        return (s0, None)
    _, kind, m = sorted(candidates, key=lambda t: t[0])[0]
    pure = s0[: m.start()].strip()
    # mypy: the regex has a named group "letter", assert non-None then normalize
    raw_letter = m.group("letter")
    assert raw_letter is not None
    letter = _strip_primes(raw_letter) or ""
    title = (m.group("title") or "").strip()
    return (pure, (kind, letter, title))


# ---------------------------------------------------------------------
# Title capture (conservative single-line, as in your working version)
# ---------------------------------------------------------------------

_CAP_START = re.compile(r"^[A-ZΑ-ΩΆ-Ώ]", re.UNICODE)


def _pick_single_line_title(body_lines: list[str], inline: str | None) -> tuple[str | None, int]:
    """
    Συντηρητική επιλογή τίτλου:
      1) Αν υπάρχει inline τίτλος μετά το 'Άρθρο Ν:', τον κρατάμε όπως είναι.
      2) Αλλιώς, κοιτάμε ΜΟΝΟ την επόμενη μη κενή γραμμή:
         - να μην είναι 'Άρθρο …' / ΜΕΡΟΣ / ΤΙΤΛΟΣ / ΚΕΦΑΛΑΙΟ / ΤΜΗΜΑ
         - να μην είναι bullet
         - να ξεκινά με κεφαλαίο
         - να μην είναι υπερβολικά μεγάλη (> 180 χαρακτήρες)
      3) Αν επιλεγεί, καταναλώνουμε μόνο αυτή τη μία γραμμή (+ ένα προαιρετικό κενό).
    """
    inline_norm = (inline or "").strip()
    if inline_norm:
        return (inline_norm, 0)  # δεν αφαιρούμε τίποτα από body_lines

    k = _find_next_nonempty(body_lines, 0)
    if k is None:
        return (None, 0)

    cand = (body_lines[k] or "").strip()

    if ARTICLE_START_RX.match(cand):  # νέο άρθρο
        return (None, 0)
    if (
        PART_RE.match(cand)
        or TITLE_RE.match(cand)
        or CHAPTER_RE.match(cand)
        or SECTION_RE.match(cand)
    ):
        return (None, 0)
    if _is_bullet(cand):
        return (None, 0)
    if len(cand) > 180:
        return (None, 0)
    if not _CAP_START.match(cand):
        return (None, 0)

    consumed = k + 1
    # προαιρετικό κενό αμέσως μετά
    if consumed < len(body_lines) and not (body_lines[consumed] or "").strip():
        consumed += 1

    return (cand, consumed)


# ---------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------


def find_articles_in_text(text: str) -> list[tuple[int, int, str | None]]:
    lines = _splitlines_preserve(text)
    out: list[tuple[int, int, str | None]] = []
    for i, ln in enumerate(lines):
        m = ARTICLE_HEADING_RX.match(ln)
        if not m:
            continue
        num = int(m.group("num"))
        inline = (m.group("inline") or "").strip() or None
        out.append((i, num, inline))
    return out


# ---------------------------------------------------------------------
# Core scanning (hierarchy; SECTION added; multi-line header titles)
# ---------------------------------------------------------------------
def _collect_contexted_heads(
    tokens: list[str], base_ctx: dict[str, Any] | None = None
) -> tuple[list[_Head], dict[tuple[int, int], dict[str, Any]]]:
    if not all(isinstance(t, str) for t in tokens):
        raise TypeError("Expected list[str] for tokens (text lines).")

    ctx: dict[str, Any] = dict(base_ctx or {})
    map_ctx: dict[tuple[int, int], dict[str, Any]] = {}
    heads: list[_Head] = []

    for i, ln in enumerate(tokens):
        # ---- ΜΕΡΟΣ ----
        m = PART_RE.match(ln)
        if m:
            ctx["part_letter"] = _strip_primes(m.group("letter"))
            base = (m.group("title") or "").strip()

            # NEW: split out inline TITLE/CHAPTER/SECTION from the same line
            pure_part, inline_struct = _split_off_inline_structural(base)

            # Only extend into next lines if we *didn't* see an inline header on this line
            if inline_struct is None:
                extra, _ = _extend_header_title(tokens, i + 1)
                ctx["part_title"] = (
                    pure_part + (" " if pure_part and extra else "") + extra
                ).strip() or None
            else:
                ctx["part_title"] = pure_part or None
                kind, letter, t0 = inline_struct
                if kind == "title":
                    ctx["title_letter"] = letter
                    extra_t, _ = _extend_header_title(tokens, i + 1) if not t0 else ("", 0)
                    ctx["title_title"] = (
                        t0 + (" " if t0 and extra_t else "") + extra_t
                    ).strip() or None
                    ctx["chapter_letter"] = None
                    ctx["chapter_title"] = None
                    ctx["section_letter"] = None
                    ctx["section_title"] = None
                elif kind == "chapter":
                    ctx["chapter_letter"] = letter
                    extra_t, _ = _extend_header_title(tokens, i + 1) if not t0 else ("", 0)
                    ctx["chapter_title"] = (
                        t0 + (" " if t0 and extra_t else "") + extra_t
                    ).strip() or None
                    ctx["section_letter"] = None
                    ctx["section_title"] = None
                elif kind == "section":
                    ctx["section_letter"] = letter
                    extra_t, _ = _extend_header_title(tokens, i + 1) if not t0 else ("", 0)
                    ctx["section_title"] = (
                        t0 + (" " if t0 and extra_t else "") + extra_t
                    ).strip() or None
            continue

        # ---- ΤΙΤΛΟΣ ----
        m = TITLE_RE.match(ln)
        if m:
            ctx["title_letter"] = _strip_primes(m.group("letter"))
            base = (m.group("title") or "").strip()
            extra, _ = _extend_header_title(tokens, i + 1) if not base else ("", 0)
            title = (base + (" " if base and extra else "") + extra).strip()
            ctx["title_title"] = title or None
            # reset downstream
            ctx["chapter_letter"] = None
            ctx["chapter_title"] = None
            ctx["section_letter"] = None
            ctx["section_title"] = None
            continue

        # ---- ΚΕΦΑΛΑΙΟ ----
        m = CHAPTER_RE.match(ln)
        if m:
            ctx["chapter_letter"] = _strip_primes(m.group("letter"))
            base = (m.group("title") or "").strip()
            extra, _ = _extend_header_title(tokens, i + 1) if not base else ("", 0)
            title = (base + (" " if base and extra else "") + extra).strip()
            ctx["chapter_title"] = title or None
            # reset section
            ctx["section_letter"] = None
            ctx["section_title"] = None
            continue

        # ---- ΤΜΗΜΑ ----
        m = SECTION_RE.match(ln)
        if m:
            ctx["section_letter"] = _strip_primes(m.group("letter"))
            base = (m.group("title") or "").strip()
            extra, _ = _extend_header_title(tokens, i + 1) if not base else ("", 0)
            title = (base + (" " if base and extra else "") + extra).strip()
            ctx["section_title"] = title or None
            continue

        # ---- ΑΡΘΡΟ ----
        m = ARTICLE_HEADING_RX.match(ln)
        if m:
            num = int(m.group("num"))
            inline = (m.group("inline") or "").strip() or None
            h: _Head = {"idx": i, "num": num, "inline": inline}
            heads.append(h)
            map_ctx[(i, num)] = dict(ctx)
            continue

    return heads, map_ctx


# ---------------------------------------------------------------------
# Public: text/tokens → articles
# ---------------------------------------------------------------------


def extract_articles(tokens: Iterable[str]) -> dict[str, dict[str, Any]]:
    lines = [s if isinstance(s, str) else str(s) for s in tokens]
    if not all(isinstance(s, str) for s in lines):
        raise TypeError("extract_articles() expects an iterable of str (text lines).")

    heads, map_ctx = _collect_contexted_heads(lines, base_ctx=None)
    heads = _dedupe_and_skip_toc(heads, lines)

    out: dict[str, dict[str, Any]] = {}
    for h_i, h in enumerate(heads):
        idx = h["idx"]
        num = h["num"]
        inline = h["inline"]
        next_idx = heads[h_i + 1]["idx"] if h_i + 1 < len(heads) else len(lines)

        body_lines = lines[idx:next_idx]

        if body_lines and ARTICLE_START_RX.match(body_lines[0]):
            body_lines = body_lines[1:]

        # --- DEBUG: show raw body lines before title picking/trim ---
        global _DBG_CUR_ARTNO
        _DBG_CUR_ARTNO = num
        _dbg(f"\n=== Article {num} ===")
        _dbg("Body lines BEFORE title pick:")
        for i, s in enumerate(body_lines):
            _dbg(f"  [{i:03d}] {repr(s)}")

        title_text, consumed = _pick_single_line_title(body_lines, inline)
        body_lines = body_lines[consumed:]
        _dbg(f"Consumed for title: {consumed} ; picked title: {repr(title_text)}")

        # drop trailing PART/TITLE/CHAPTER/SECTION chunk if present
        before_len = len(body_lines)
        body_lines = _trim_trailing_structural_block(body_lines)
        after_len = len(body_lines)
        _dbg(f"Lines after trailing-structural trim: {after_len} (was {before_len})")
        if after_len != before_len:
            _dbg("Body lines AFTER trim:")
            for i, s in enumerate(body_lines):
                _dbg(f"  [{i:03d}] {repr(s)}")

    return out


def build_articles_map(text: str, ctx: Ctx | None = None) -> dict[str, Any]:
    lines = _splitlines_preserve(text)

    base_ctx = _ctx_to_dict(ctx) if ctx is not None else {}
    heads, map_ctx = _collect_contexted_heads(lines, base_ctx=base_ctx)
    heads = _dedupe_and_skip_toc(heads, lines)

    out: dict[str, Any] = {}
    for h_i, h in enumerate(heads):
        idx = h["idx"]
        num = h["num"]
        inline = h["inline"]
        next_idx = heads[h_i + 1]["idx"] if h_i + 1 < len(heads) else len(lines)

        body_lines = lines[idx:next_idx]

        if body_lines and ARTICLE_START_RX.match(body_lines[0]):
            body_lines = body_lines[1:]

        # --- DEBUG: show raw body lines before title picking/trim ---
        global _DBG_CUR_ARTNO
        _DBG_CUR_ARTNO = num
        _dbg(f"\n=== build_articles_map(): Article {num} ===")
        _dbg("Body lines BEFORE title pick:")
        for i, s in enumerate(body_lines):
            _dbg(f"  [{i:03d}] {repr(s)}")

        title_text, consumed = _pick_single_line_title(body_lines, inline)
        body_lines = body_lines[consumed:]
        _dbg(f"Consumed for title: {consumed} ; picked title: {repr(title_text)}")

        # drop trailing PART/TITLE/CHAPTER/SECTION chunk if present
        before_len = len(body_lines)
        body_lines = _trim_trailing_structural_block(body_lines)
        after_len = len(body_lines)
        _dbg(f"Lines after trailing-structural trim: {after_len} (was {before_len})")
        if after_len != before_len:
            _dbg("Body lines AFTER trim:")
            for i, s in enumerate(body_lines):
                _dbg(f"  [{i:03d}] {repr(s)}")

        html_body = lines_to_html(body_lines)

        new_title, new_html = balance_subtitle_with_body(title_text or "", html_body)
        new_html = stitch_article_range_stub_upstream(new_html)

        full_title, new_html = apply_title_body_fixups(num, new_title or "", new_html)

        model_art = ModelArticle(
            number=str(num),
            title=full_title,
            html=new_html,
            context=_dict_to_ctx(map_ctx.get((idx, num))),
        )
        out[str(num)] = _article_model_to_record_dict(model_art)

    return out


def build_articles(text: str, ctx: Ctx | None = None) -> list[dict[str, Any]]:
    lines = _splitlines_preserve(text)
    base_ctx = _ctx_to_dict(ctx) if ctx is not None else {}
    heads, _ = _collect_contexted_heads(lines, base_ctx=base_ctx)
    heads = _dedupe_and_skip_toc(heads, lines)

    out_list: list[dict[str, Any]] = []
    for h_i, h in enumerate(heads):
        idx = h["idx"]
        num = h["num"]
        inline = h["inline"]
        next_idx = heads[h_i + 1]["idx"] if h_i + 1 < len(heads) else len(lines)

        body_lines = lines[idx:next_idx]

        if body_lines and ARTICLE_START_RX.match(body_lines[0]):
            body_lines = body_lines[1:]
            start_line = idx + 1
        else:
            start_line = idx

        # --- DEBUG: show raw body lines before title picking/trim ---
        global _DBG_CUR_ARTNO
        _DBG_CUR_ARTNO = num
        _dbg(f"\n=== build_articles(): Article {num} ===")
        _dbg(f"Slice idx={idx}..{next_idx} (start_line initial: {start_line})")
        _dbg("Body lines BEFORE title pick:")
        for i, s in enumerate(body_lines):
            _dbg(f"  [{i:03d}] {repr(s)}")

        title_text, consumed = _pick_single_line_title(body_lines, inline)
        _dbg(f"Consumed for title: {consumed} ; picked title: {repr(title_text)}")
        body_lines = body_lines[consumed:]
        start_line += consumed
        _dbg(f"start_line AFTER title consumption: {start_line}")

        # drop trailing PART/TITLE/CHAPTER/SECTION chunk if present
        before_len = len(body_lines)
        body_lines = _trim_trailing_structural_block(body_lines)
        after_len = len(body_lines)
        _dbg(f"Lines after trailing-structural trim: {after_len} (was {before_len})")
        if after_len != before_len:
            _dbg("Body lines AFTER trim:")
            for i, s in enumerate(body_lines):
                _dbg(f"  [{i:03d}] {repr(s)}")

        html_body = lines_to_html(body_lines)
        new_title, new_html = balance_subtitle_with_body(title_text or "", html_body)
        new_html = stitch_article_range_stub_upstream(new_html)
        full_title, new_html = apply_title_body_fixups(num, new_title or "", new_html)

        body_txt = re.sub(r"</?(?:p|ul|li)>", "\n", new_html)
        body_txt = re.sub(r"\n{3,}", "\n\n", body_txt).strip()

        out_list.append(
            {
                "number": num,
                "title": (
                    full_title.replace(f"Άρθρο {num}: ", "", 1)
                    if full_title.startswith(f"Άρθρο {num}: ")
                    else full_title
                ),
                "body": body_txt,
                "start_line": start_line,
                "end_line": next_idx,
            }
        )

    return out_list
