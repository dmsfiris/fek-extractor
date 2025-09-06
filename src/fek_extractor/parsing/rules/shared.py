# src/fek_extractor/parsing/rules/shared.py
from __future__ import annotations

import re
from re import Match

from ..heuristics import (
    begins_with_lower_alpha,
    find_finite_verb_index,
    has_finite_verb_hint,
    heading_candidate,
    prev_ends_connector,
)
from ..html_blocks import iter_block_texts, strip_leading_block_with_text

__all__ = [
    # regexes you expose
    "FIRST_P_RE",
    "UL_HEAD_RE",
    "FIRST_LI_TEXT_RE",
    "ALL_LI_TEXT_RE",
    "NUM_MARKER_RE",
    "LEGAL_ANCHOR_RE",
    "CAPITAL_START_RE",
    "PREP_EARLY_RE",
    "DET_TRAIL_RE",
    "SECOND_P_RE",
    # new shared regexes/helpers
    "LIST_HEAD_RE",
    "FIRST_LI_TEXT_FALLBACK_RE",
    "EARLY_PREP_RE",
    "LEADING_GEN_CONT_RE",
    "CONT_TAIL_PREP_OR_ART_RE",
    "CONT_TAIL_ART_PLUS_WORD_RE",
    "SENT_STARTER_RE",
    "TRAILING_SEP_RE",
    "FIRSTP_EARLY_PREP_RE",
    # functions/helpers you expose
    "norm_ws",
    "norm_lower",
    "norm_tokens",
    "first_li_text",
    "first_li_text_robust",
    "is_list_head",
    "is_numbered_lead",
    "early_li_texts",
    "lift_from_html",
    "word_count",
    "parse_first_p",
    "starts_with_legal_anchor",
    "is_balanced_paren_block",
    "same_as_first_li_text",
    "is_headingish_np",
    "ends_with_stop_tail",
    "needs_continuation_tail",
    "trim_trailing_seps",
    "strip_leading_article",
    "balance_subtitle_with_body",
    "stitch_article_range_stub_upstream",
    # re-exports from heuristics.py
    "begins_with_lower_alpha",
    "has_finite_verb_hint",
    "find_finite_verb_index",
    "heading_candidate",
    "prev_ends_connector",
    "iter_block_texts",
    "strip_leading_block_with_text",
]

# ---------- Regexes (existing) ----------

FIRST_P_RE: re.Pattern[str] = re.compile(
    r"^\s*<p>(?P<p>.*?)</p>(?P<rest>.*)$",
    re.DOTALL,
)
UL_HEAD_RE: re.Pattern[str] = re.compile(
    r"^\s*<ul>(?P<ul>.*?)</ul>(?P<rest>.*)$",
    re.DOTALL,
)
FIRST_LI_TEXT_RE: re.Pattern[str] = re.compile(
    r"<li>\s*(?P<t>.*?)\s*</li>",
    re.DOTALL,
)
ALL_LI_TEXT_RE: re.Pattern[str] = re.compile(
    r"<li>\s*(?P<t>.*?)\s*</li>",
    re.DOTALL,
)

NUM_MARKER_RE: re.Pattern[str] = re.compile(
    r"(?:(?<=^)|(?<=\s))(?P<m>\d{1,2}[.)])\s+",
    re.DOTALL,
)

LEGAL_ANCHOR_RE: re.Pattern[str] = re.compile(
    r"(?x)\b("
    r"Στο\s+άρθρο\b"
    r"|Στο\s+τέλος\s+της\s+παρ\.\b"
    r"|Στην\s+παρ\.\b"
    r"|Η\s+παρ\.\s*\d+\s+αντικαθίσταται\b"
    r"|Επέρχονται\b|επέρχονται\b"
    r"|Τροποποιείται\b|τροποποιείται\b"
    r")",
    re.UNICODE,
)

# Include accented Greek capitals too (Ά Έ Ή Ί Ό Ύ Ώ)
CAPITAL_START_RE: re.Pattern[str] = re.compile(r"[A-ZΑ-ΩΆΈΉΊΌΎΏ]")

# Early capitalized preposition after the first token (case-sensitive)
PREP_EARLY_RE: re.Pattern[str] = re.compile(r"^(?:\S+)\s+(?:Για|Με|Κατά|Σύμφωνα|Προς|Ως|Σε|Από)\b")

BOUNDARY_CHARS = r"-—–«»“”'\":;,·\s" + "\u00a0\u202f\u2011"
DET_TRAIL_RE: re.Pattern[str] = re.compile(
    r"(?:^|[" + BOUNDARY_CHARS + r"])"
    r"(?P<det>(?:Ο|Η|Το|Οι|Τα|Τον|Την|Τη|Του|Της|Τους|Τις|Των)\s+\S.{0,200}?)"
    r"(?=$|[" + BOUNDARY_CHARS + r"])",
    re.DOTALL,
)

SECOND_P_RE: re.Pattern[str] = re.compile(
    r"^\s*<p>(?P<p2>.*?)</p>(?P<rest2>.*)$",
    re.DOTALL,
)

# ---------- New shared helpers / regexes (centralized) ----------

# Robust list detection and first <li> text fallback
LIST_HEAD_RE: re.Pattern[str] = re.compile(r"(?is)^\s*<ul\b")
FIRST_LI_TEXT_FALLBACK_RE: re.Pattern[str] = re.compile(r"(?is)<li>\s*([^<]{1,400})")

# Early Greek prepositions often indicate the glued start of body text
EARLY_PREP_RE: re.Pattern[str] = re.compile(
    r"(?:Για|Με|Κατά|Σύμφωνα|Προς|Ως|Σε|Από)\b",
    re.IGNORECASE,
)

# Leading genitive continuation (relaxed): starts with του/της/των and then
# a determiner begins the next sentence.
LEADING_GEN_CONT_RE: re.Pattern[str] = re.compile(
    r"""^(?P<cont>\s*(?:του|της|των)\s+(?:[^,.:;…<]{1,80}?))\s+
        (?=(?:ο|η|το|οι|τα|τον|την|το|στον|στην|στο|στους|στις|στα|στη|στην)\b)""",
    re.IGNORECASE | re.VERBOSE,
)

# Generic Greek “needs continuation” tails
CONT_TAIL_PREP_OR_ART_RE: re.Pattern[str] = re.compile(
    r"(?:\b(?:από|προς|για|με|σε|κατά|υπέρ|υπό|χωρίς|ως|έως|μέχρι|ανά|διά|δια|επί|περί|"
    r"μεταξύ)\b|\b(?:ο|η|το|οι|τα|του|της|των|τον|την|το|στον|στην|στο|στους|στις|στα|"
    r"στη|στην))\s*$",
    re.IGNORECASE,
)
CONT_TAIL_ART_PLUS_WORD_RE: re.Pattern[str] = re.compile(
    r"\b(?:ο|η|το|οι|τα|του|της|των|τον|την|το|στον|στην|στο|στους|στις|στα|στη|στην)\s+"
    r"[Α-ΩΆ-Ώα-ωάέήίόύώϊΐϋΰ][^,.:;…]{1,40}\s*$",
    re.IGNORECASE,
)

# Sentence starters common in Greek (for first <li>)
SENT_STARTER_RE: re.Pattern[str] = re.compile(
    r"^(Για|Με|Κατά|Σύμφωνα|Προς|Ως|Σε|Από|Εφόσον|Όταν|Καθώς|Λόγω|Επειδή)\b",
    re.IGNORECASE,
)

# Trailing separators like ":" "·" etc.
TRAILING_SEP_RE: re.Pattern[str] = re.compile(r"[\s:·\.\-–—]+$")

# First-<p> early-preposition splitter (heading + body in one <p>)
FIRSTP_EARLY_PREP_RE: re.Pattern[str] = re.compile(
    r"^(?P<head>[^,.:;]{1,200}?)\s+(?P<prep>" + EARLY_PREP_RE.pattern + r")(?P<tail>.*)$",
    re.DOTALL | re.IGNORECASE,
)

# ---------- Helpers (existing + new) ----------


def norm_ws(s: str | None) -> str:
    import re as _re

    return _re.sub(r"\s+", " ", (s or "")).strip()


def norm_lower(s: str | None) -> str:
    import re as _re

    return _re.sub(r"\s+", " ", (s or "")).strip().lower()


def norm_tokens(s: str, n: int = 3) -> list[str]:
    import re as _re

    s = _re.sub(r"[«»\"'(){}\[\],;:·—–\-]", " ", s)
    s = _re.sub(r"\s+", " ", s).strip().lower()
    return s.split()[:n]


def first_li_text(html: str) -> str | None:
    m = FIRST_LI_TEXT_RE.search(html)
    if not m:
        return None
    t = re.sub(r"\s+", " ", m.group("t")).strip()
    return t or None


def first_li_text_robust(html: str) -> str:
    """Use first_li_text; fallback to a permissive capture if needed."""
    s = first_li_text(html or "")
    if s:
        return s
    m = FIRST_LI_TEXT_FALLBACK_RE.search(html or "")
    return m.group(1).strip() if m else ""


def is_list_head(html: str) -> bool:
    return bool(LIST_HEAD_RE.match(html or ""))


def is_numbered_lead(p: str) -> bool:
    return bool(re.match(r"^\s*(?:\(?[0-9ivxlcdmIVXLCDM]+\)?\.|\d+\))\s", p or ""))


def early_li_texts(html: str, limit: int = 10) -> set[str]:
    out: set[str] = set()
    for i, m in enumerate(ALL_LI_TEXT_RE.finditer(html)):
        if i >= limit:
            break
        t = norm_ws(m.group("t"))
        if t:
            out.add(t)
    return out


def lift_from_html(html: str) -> str | None:
    """
    Return first clean heading-like block text from early HTML blocks, else None.
    Never lift a block that equals a <li> text (normalized).
    """
    li_forbidden = early_li_texts(html, limit=10)
    for text in iter_block_texts(html, limit=6):
        norm = norm_ws(text)
        if not norm or norm in li_forbidden:
            continue
        if heading_candidate(text):
            return text
    return None


def word_count(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


def parse_first_p(html: str) -> tuple[str | None, str, Match[str] | None]:
    m = FIRST_P_RE.match(html) or FIRST_P_RE.search(html)
    if not m:
        return None, html, None
    return (m.group("p") or "").strip(), (m.group("rest") or ""), m


def starts_with_legal_anchor(s: str) -> bool:
    t = re.sub(r"^[\s«»\"'(){}\[\],;:·—–\-]+", "", s or "").lstrip()
    return bool(LEGAL_ANCHOR_RE.match(t))


def is_balanced_paren_block(s: str, max_len: int = 200) -> bool:
    t = re.sub(r"<[^>]+>", "", s or "").strip().strip("«»“”\"'\u00a0\u202f")
    if not (t.startswith("(") and t.endswith(")")):
        return False
    depth = 0
    for ch in t:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and len(t) <= max_len


def same_as_first_li_text(s: str | None, html: str) -> bool:
    li = first_li_text(html)
    return norm_ws(s) == norm_ws(li)


def is_headingish_np(s: str, allow_short_verbal: bool = False) -> bool:
    """
    Heading-like noun phrase:
      - passes heading_candidate()
      - does not end with connector
      - by default: has no finite verb hint
      - if allow_short_verbal=True, allow ≤6 words verbal headings without terminal punctuation
    """
    if not s or not heading_candidate(s) or prev_ends_connector(s):
        return False
    if allow_short_verbal:
        if has_finite_verb_hint(s):
            return (word_count(s) <= 6) and not s.endswith((".", "·", ":", ";"))
        return True
    return not has_finite_verb_hint(s)


# ---------- Generic guards (use in splitters & title rules) ----------

_ART_RE: re.Pattern[str] = re.compile(
    r"^(?:Τα|Οι|Η|Ο|Το|Τη|Την|Της|Του)\s+(?P<rest>.+)$",
    re.IGNORECASE,
)

STOP_TAIL: set[str] = {
    # articles / determiners
    "τα",
    "οι",
    "η",
    "ο",
    "το",
    "τη",
    "την",
    "της",
    "του",
    "των",
    # small function words / preps / conj / negation
    "μη",
    "με",
    "σε",
    "ως",
    "για",
    "κατά",
    "προς",
    "από",
    "χωρίς",
    "λόγω",
    "μετά",
    "πριν",
    "εντός",
    "εκτός",
    "έως",
    "έναντι",
    "και",
    "ή",
    # articulated forms
    "στο",
    "στη",
    "στην",
    "στον",
    # accusative articles
    "τον",
}


def ends_with_stop_tail(head: str) -> bool:
    """True if the last token of `head` is a weak/functional word (generic guard)."""
    toks = (head or "").split()
    if not toks:
        return True
    last = re.sub(r"[^\wΑ-Ωα-ω]", "", toks[-1]).lower()
    return last in STOP_TAIL


def needs_continuation_tail(s: str) -> bool:
    if CONT_TAIL_PREP_OR_ART_RE.search(s or ""):
        return True
    if CONT_TAIL_ART_PLUS_WORD_RE.search(s or ""):
        return True
    return bool(prev_ends_connector(s or ""))


def trim_trailing_seps(s: str) -> str:
    return TRAILING_SEP_RE.sub("", s or "").strip()


def strip_leading_article(s: str) -> str:
    m = _ART_RE.match(s or "")
    if not m:
        return s
    rest = (m.group("rest") or "").strip()
    if rest.lower().startswith("μη "):
        rest = rest[:1].upper() + rest[1:]
    return rest


# --- BEGIN: upstream subtitle/body normalization helpers ---

# Ζεύγη οριοθετών που “ανοίγουν/κλείνουν” σε FEK τίτλους
_DELIM_PAIRS: list[tuple[str, str]] = [
    ("(", ")"),
    ("«", "»"),
    ("“", "”"),
]
# Θεωρούμε κι ASCII μονά/διπλά, ως ζεύγη με count%2
_ASCII_QUOTES: list[str] = ['"', "'"]


def _is_unbalanced_open(s: str) -> bool:
    """
    True αν στο s υπάρχουν “ανοικτοί” οριοθέτες (π.χ. '(' χωρίς ')', '«' χωρίς '»')
    ή “μονός” αριθμός ASCII εισαγωγικών.
    """
    t = s or ""
    # Παρενθέσεις/εισαγωγικά ζεύγη
    for left, right in _DELIM_PAIRS:
        if t.count(left) > t.count(right):
            return True
    # ASCII quotes: μονός αριθμός => ανοικτό
    return any(t.count(q) % 2 == 1 for q in _ASCII_QUOTES)


def balance_subtitle_with_body(
    subtitle: str | None,
    html: str,
    max_blocks: int = 3,
) -> tuple[str | None, str]:
    """
    Αν ο υπότιτλος αφήνει “ανοικτούς” οριοθέτες, τραβά διαδοχικά έως `max_blocks`
    πρώτα <p> blocks από το `html` και τα ενώνει στον υπότιτλο μέχρι να ισορροπήσει.
    """
    s = (subtitle or "").strip()
    if not s or not _is_unbalanced_open(s):
        return subtitle, html

    rest_html = html
    taken: list[str] = []
    for _ in range(max_blocks):
        m = FIRST_P_RE.match(rest_html) or FIRST_P_RE.search(rest_html)
        if not m:
            break
        p = (m.group("p") or "").strip()
        rest_html = m.group("rest") or ""
        if not p:
            break
        taken.append(p)
        s = (s + " " + p).strip()
        if not _is_unbalanced_open(s):
            return s, rest_html

    # αν δεν ισορρόπησε, γύρνα όπως έχει
    return s, rest_html if taken else html


def stitch_article_range_stub_upstream(html: str) -> str:
    """
    General stub stitcher.

    If the first <p> lacks terminal punctuation, stitch it with the next <p> when that
    looks like a continuation. Optionally pull a 3rd <p> when it begins lowercase or
    when the stitched text still has unbalanced delimiters/quotes.
    """
    first_p, rest, _ = parse_first_p(html)
    if not first_p:
        return html

    p1 = first_p.strip()

    # your simplified criterion: “no terminal punctuation” is enough to treat as stub
    def _looks_stub(s: str) -> bool:
        return bool(s and not re.search(r"[.:;…·]\s*$", s))

    if not _looks_stub(p1):
        return html

    m2 = SECOND_P_RE.match(rest) or SECOND_P_RE.search(rest)
    if not m2:
        return html

    p2 = (m2.group("p2") or "").strip()
    rest2 = m2.group("rest2") or ""

    def _looks_cont(s: str) -> bool:
        if not s:
            return False
        # lowercase start is a strong continuation signal
        if begins_with_lower_alpha(s):
            return True
        # range continuation tokens
        if re.match(r"^(?:έως|ως|μέχρι)\b", s, flags=re.IGNORECASE):
            return True
        # number / number-range / simple list (27 | 27-30 | 27 — 30 | 27, 28)
        if re.match(
            r"^\d{1,3}(?:\s*[–—-]\s*\d{1,3})?(?:\s*(?:,|και)\s*\d{1,3})*",
            s,
        ):
            return True
        # short, non-verbal, non-terminal phrase as a fallback
        if not has_finite_verb_hint(s) and not re.search(r"[.:;…·]\s*$", s):
            return len(s.split()) <= 6
        return False

    if not _looks_cont(p2):
        return html

    stitched = re.sub(r"\s+", " ", (p1 + " " + p2)).strip()

    # Optionally pull a 3rd <p> if:
    # - it begins lowercase, OR
    # - the stitched text still has unbalanced delimiters, OR
    # - p2 was extremely short (≤ 2 words)
    m3 = SECOND_P_RE.match(rest2) or SECOND_P_RE.search(rest2)
    if not m3:
        return f"<p>{stitched}</p>{rest2}"

    p3 = (m3.group("p2") or "").strip()
    rest3 = m3.group("rest2") or ""
    pull_third = (
        bool(p3 and begins_with_lower_alpha(p3))
        or _is_unbalanced_open(stitched)
        or len(p2.split()) <= 2
    )
    if pull_third:
        stitched = re.sub(r"\s+", " ", (stitched + " " + p3)).strip()
        return f"<p>{stitched}</p>{rest3}"

    return f"<p>{stitched}</p>{rest2}"
