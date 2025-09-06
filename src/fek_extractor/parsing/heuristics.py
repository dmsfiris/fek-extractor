# src/fek_extractor/parsing/heuristics.py
from __future__ import annotations

import re
import unicodedata

__all__ = [
    "heading_candidate",
    "prev_ends_connector",
    "has_finite_verb_hint",
    "find_finite_verb_index",
    "begins_with_lower_alpha",
]

# ---------------------------------------------------------------------------
# Character classes / small utilities
# ---------------------------------------------------------------------------

# Greek + Latin lowercase ranges (for light morphological checks)
_GREEK_LOWER = "α-ωάέήίόύώϊΐϋΰ"
_LATIN_LOWER = "a-z"
_LOWER = _LATIN_LOWER + _GREEK_LOWER

# Normalize-ish strip of leading punctuation commonly found before headings
_LEAD_PUNCT_RE = re.compile(r'^[\s«»"“”\'‘’(){}\[\],;:·—–\-]+')
# Allow quick “capital start” check after punctuation trim
_CAPITAL_START_RE = re.compile(r"[Α-ΩA-Z]")

# Lowercase-start detection (used for “looks like continuation” elsewhere)
_LOWER_START_RE = re.compile(rf"[{_LOWER}]")


def begins_with_lower_alpha(s: str) -> bool:
    t = (_LEAD_PUNCT_RE.sub("", s or "")).lstrip()
    return bool(t) and bool(_LOWER_START_RE.match(t))


# ---------------------------------------------------------------------------
# Bulletish / list-marker exclusion (for headings)
# ---------------------------------------------------------------------------

# Disallow lines that clearly start like a list item (dash, digit, roman, greek α) …)
_BULLETISH_START_RE = re.compile(
    r"""(?x)
    ^\s*(?:                               # start of line + optional spaces
         [-•]                             # dash/bullet
         | \d{1,3}[.)]                    # 1)  1.
         | \(?[ivxIVX]+\)                 # (i) (iv) (x) …
         | \(?[α-ωΑ-Ω]\)                  # (α) (β) …
    )\s+
    """
)


# ---------------------------------------------------------------------------
# “Connector tails”: titles shouldn't end with weak linkers (πχ «… με», «… του»)
# ---------------------------------------------------------------------------

_CONNECTOR_TAILS = {
    # prepositions
    "της",
    "του",
    "των",
    "για",
    "κατά",
    "κατ’",
    "κατ'",
    "σε",
    "με",
    "ως",
    "από",
    "προς",
    "χωρίς",
    "επί",
    "εντός",
    "εκτός",
    "υπέρ",
    "καθ’",
    "καθ'",
    "ανά",
    "διά",
    "δια",
    # articles / clitics
    "ο",
    "η",
    "το",
    "οι",
    "τα",
    "τον",
    "την",
    "τη",
    "τους",
    "τις",
    # split 'στ-' forms
    "στο",
    "στον",
    "στα",
    "στους",
    "στη",
    "στην",
    "στις",
}

_CONNECTOR_PREPS = {
    "με",
    "για",
    "σε",
    "κατά",
    "ως",
    "χωρίς",
    "προς",
    "ανά",
    "διά",
    "εκτός",
    "εντός",
    "υπέρ",
    "καθ’",
    "καθ'",
    "κατ’",
    "κατ'",
    "σύμφωνα",
}

_CONNECTOR_ARTS = {
    "ο",
    "η",
    "το",
    "οι",
    "τα",
    "τον",
    "την",
    "τη",
    "τους",
    "τις",
    "του",
    "της",
    "των",
    "στο",
    "στον",
    "στα",
    "στους",
    "στη",
    "στην",
    "στις",
}


def prev_ends_connector(prev: str) -> bool:
    """
    True if 'prev' ends in a small linker (article/preposition) or a prep+article
    bigram (e.g. 'με το', 'για την'), including 'σύμφωνα με'.
    """
    tokens = re.findall(r"[A-Za-zΑ-Ωα-ωΆ-Ώά-ώ]+", (prev or "").strip())
    if not tokens:
        return False

    last = tokens[-1].lower()
    if last in _CONNECTOR_TAILS:
        return True

    if len(tokens) >= 2:
        a = tokens[-2].lower()
        b = last
        return (a in _CONNECTOR_PREPS and b in _CONNECTOR_ARTS) or bool(
            a == "σύμφωνα" and b == "με"
        )

    return False


# ---------------------------------------------------------------------------
# Legal-citation detection (drop these as titles)
# ---------------------------------------------------------------------------

_CITATION_RES: list[re.Pattern[str]] = [
    # ν. 4548/2018, Ν. 2190/1920
    re.compile(r"\bν\.\s*\d+/\d{2,4}\b", re.IGNORECASE | re.UNICODE),
    # π.δ. 123/2017
    re.compile(r"\bπ\.δ\.\s*\d+/\d{2,4}\b", re.IGNORECASE | re.UNICODE),
    # άρθρο 3, άρθρα 1 έως 5, αρ. 12, παρ. 4
    re.compile(
        r"(?:\bάρθρ\w*\s+\d+[Α-ΩA-Z]?\b|\bαρ\.\s*\d+\b|\bπαρ\.\s*\d+\b)",
        re.IGNORECASE | re.UNICODE,
    ),
    # FEK style parenthetical refs: (Α΄ 176) , (Α’ 136/17.07.2020)
    re.compile(
        r"\(\s*[Α-ΩA-Z][΄'′`´ʹʹ]?\s*\d+(?:\s*/\s*\d{2}\.\d{2}\.\d{4})?\s*\)",
        re.IGNORECASE | re.UNICODE,
    ),
]


# ---------------------------------------------------------------------------
# Heading candidate
# ---------------------------------------------------------------------------

# Capitalized Greek prepositions that commonly start body sentences, not headings.
_PREP_LINE_RE = re.compile(r"^(?:Για|Με|Κατά|Σύμφωνα|Προς|Ως|Σε|Από)\b")


def heading_candidate(s: str) -> bool:
    """
    Conservative check: suitable as an article subtitle/headline.

    Reject if:
      - empty or bulletish start,
      - too long (chars/words),
      - starts with a capitalized preposition (e.g., 'Για', 'Με', …),
      - ends with a weak connector («… με», «… του», …).
    """
    t = unicodedata.normalize("NFC", (s or "")).strip()
    if not t:
        return False
    if _BULLETISH_START_RE.match(t):
        return False

    # Quick size limits
    words = len(re.findall(r"\S+", t))
    if words > 20 or len(t) > 140:
        return False

    # Prefer capitalish start after leading punctuation (soft preference only)
    lead_trim = _LEAD_PUNCT_RE.sub("", t)

    # Hard reject: lines that begin with a capitalized preposition (these are usually body openers)
    if lead_trim and _PREP_LINE_RE.match(lead_trim):
        return False

    # Final guard: no trailing connector like “… του/της/με/και …”
    return not prev_ends_connector(t)


# ---------------------------------------------------------------------------
# Verb-ish (finite verb) detection for better title/body splitting
# ---------------------------------------------------------------------------

_VERB_SUFFIX_RE = re.compile(
    rf"\b[{_LOWER}]{{3,}}"
    r"(?:"
    r"ω|ώ|"
    r"ει|εί(?!ναι)|"
    r"ουμε|ούμε|"
    r"ετε|είτε|"
    r"ουν(?:ε)?|ούν(?:ε)?|"
    r"ομαι|όμαστε|εσαι|εστε|"
    r"εται|ται|"
    r"ούνται|ονται|νται|"
    r"ήθη(?:κα|καν)?|"
    r"ησε|ησαν|ηκε"
    r")\b",
    re.UNICODE,
)

_VERB_IMPERSONALS_RE = re.compile(
    r"\b("
    r"είναι|είμαι|είσαι|είμαστε|είστε|ήταν|ήμουν|"
    r"πρέπει|επιτρέπεται|απαγορεύεται|δύναται|δυναται|"
    r"οφείλει|οφείλουν|"
    r"υποχρεούται|υποχρεούνται|"
    r"ισχύει|ισχύουν|"
    r"αποτελεί|αποτελούν|"
    r"έχω|έχει|έχουν"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

_PARTICLE_VERB_RE = re.compile(
    rf"\b(θα|να|ας)\s+[{_LOWER}]{{3,}}",
    re.UNICODE,
)

# words ending in -ω/-ώ that are NOT verbs (common in legal Greek)
_NON_VERB_OMEGA = {"μέσω", "λόγω", "άνω", "κάτω", "έξω", "έσω"}

# For “index” search we’ll mask out spans we don’t want to count
_PAREN_SPAN_RE = re.compile(r"\([^)]{0,400}\)")
# Slightly “ref-y” parentheses like (Α΄ 176) / (Α’ 136/17.07.2020)
_REFY_SPAN_RE = re.compile(r"\(\s*[Α-ΩA-Z][΄'′`´ʹʹ]?\s*\d+(?:\s*/\s*\d{2}\.\d{2}\.\d{4})?\s*\)")

_OMEGA_RX = re.compile(
    r"\b(" + "|".join(map(re.escape, sorted(_NON_VERB_OMEGA))) + r")\b",
    re.UNICODE,
)


def _split_main_and_first_paren(s: str) -> tuple[str, str | None, str | None]:
    """
    Return (main, paren, after) where paren is first (...) group if present.
    """
    m = _PAREN_SPAN_RE.search(s)
    if not m:
        return s, None, None
    main = (s[: m.start()] or "").strip()
    paren = (s[m.start() : m.end()] or "").strip()
    after = (s[m.end() :] or "").strip()
    return main, paren, after


def has_finite_verb_hint(s: str) -> bool:
    """
    Heuristic: does the string likely contain a finite-verb form?
    We ignore purely bibliographic parentheticals and filter common
    false positives (e.g., «λόγω», «μέσω»).
    """
    t = unicodedata.normalize("NFC", (s or "")).lower()
    main, paren, _after = _split_main_and_first_paren(t)

    # remove non-verb omega words from the main part
    for w in _NON_VERB_OMEGA:
        main = re.sub(rf"\b{re.escape(w)}\b", " ", main)

    if _VERB_IMPERSONALS_RE.search(main):
        return True
    if _PARTICLE_VERB_RE.search(main):
        return True
    return bool(_VERB_SUFFIX_RE.search(main))


def _mask_len_preserving(s: str, rx: re.Pattern[str]) -> str:
    """Replace matches with same-length spaces so indices remain aligned."""
    return rx.sub(lambda m: " " * (m.end() - m.start()), s)


def _mask_for_index(s: str) -> str:
    """
    Prepare a copy for index search:
      - NFC normalize,
      - blank-out parenthetical/legal-ref spans,
      - blank-out known non-verbal -ω words,
      - lowercase for pattern compatibility.
    """
    t = unicodedata.normalize("NFC", s or "")
    t = _mask_len_preserving(t, _PAREN_SPAN_RE)
    t = _mask_len_preserving(t, _REFY_SPAN_RE)
    t = _mask_len_preserving(t, _OMEGA_RX)
    return t.lower()


def find_finite_verb_index(s: str) -> int | None:
    """
    Return earliest index of a finite-verb hint in the original string, or None.
    Uses the same top-level regexes to avoid duplication.
    """
    if not (s or "").strip():
        return None
    if not has_finite_verb_hint(s):
        return None

    masked = _mask_for_index(s)
    m1 = _VERB_IMPERSONALS_RE.search(masked)
    m2 = _PARTICLE_VERB_RE.search(masked)
    m3 = _VERB_SUFFIX_RE.search(masked)

    starts = [m.start() for m in (m1, m2, m3) if m]
    return min(starts) if starts else None
