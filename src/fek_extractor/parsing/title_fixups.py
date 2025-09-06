# src/fek_extractor/parsing/title_fixups.py
from __future__ import annotations

import re
from typing import Final

__all__ = [
    # public orchestrators
    "finalize_title",
    "apply_title_body_fixups",
    # reusable globals (connectors & starters)
    "CONNECTOR_WORDS",
    "CONNECTOR_TRAILING_RX",
    "SENTENCE_STARTERS_WORDS",
    "SENTENCE_STARTERS_RX",
    # individual fixups (exported for tests)
    "pull_directive_parenthetical_into_title",
    "pull_leading_lowercase_phrase_from_first_p",
    "pull_paragraph_after_connector_into_title",
    "pull_standalone_capitalized_p_into_title",
    "pull_lowercase_continuation_into_title",
]

# ---------------------------------------------------------------------------
# Patterns & globals
# ---------------------------------------------------------------------------

# Standalone parenthetical first paragraph like "(άρθρο 3α της Οδηγίας (ΕΕ) 2017/828)"
DIRECTIVE_PAREN_RX: Final[re.Pattern[str]] = re.compile(
    r"^\(?\s*άρθρο\s+\d+[α-ω]?\s+της\s+Οδηγίας\b.*?\)\s*$",
    re.IGNORECASE | re.UNICODE,
)

# Greek/Latin lowercase start (for continuation fragments)
LOWERCASE_START_RX: Final[re.Pattern[str]] = re.compile(
    r"^[«“\"'(\[]*\s*[a-zα-ωάέήίόύώϊΐϋΰ]",
    re.UNICODE,
)

# Uppercase (Greek + Latin) class for noun-phrase checks
_UPPERCLASS: Final[str] = "A-ZΑ-ΩΆ-Ώ"

# leading lowercase phrase (<=80 chars), then space, then uppercase start
LEADING_LOWER_FRAGMENT_RX: Final[re.Pattern[str]] = re.compile(
    rf"^\s*([a-zα-ωάέήίόύώϊΐϋΰ][^{_UPPERCLASS}\.\!\;\?…]{{0,80}})\s+([{_UPPERCLASS}].*)$",
    re.UNICODE,
)

# Whitespace-at-end including ZWSP/WJ/BOM
_WS_END = r"[\s\u200b\u2060\ufeff]*"

END_PUNCT_RX = re.compile(r"[.!;!?…]\s*$", re.UNICODE)

TRAILING_COLON_CLAUSE_RX: Final[re.Pattern[str]] = re.compile(
    r"^(?P<head>.+?)\s+(?P<clause>[^:]{3,}):\s*$",
    re.UNICODE,
)

# --------- GLOBAL CONNECTORS (reusable) -------------------------------------

CONNECTOR_WORDS: Final[tuple[str, ...]] = (
    "του",
    "της",
    "των",
    "την",
    "στο",
    "στον",
    "στη",
    "στην",
    "στους",
    "στις",
    "στα",
    "και",
    "ή",
    "από",
)

# right after CONNECTOR_WORDS / before CONNECTOR_TRAILING_RX
_CONNECTOR_ALT: Final[str] = "|".join(re.escape(w) for w in CONNECTOR_WORDS)

CONNECTOR_TRAILING_RX: Final[re.Pattern[str]] = re.compile(
    rf"(?:\s+\b(?:{_CONNECTOR_ALT})\b){_WS_END}$",
    re.IGNORECASE | re.UNICODE,
)

# --------- Sentence starters (also reusable) --------------------------------

SENTENCE_STARTERS_WORDS: Final[tuple[str, ...]] = (
    "Τα",
    "Η",
    "Ο",
    "Οι",
    "Το",
    "Τη",
    "Την",
    "Τον",
    "Στο",
    "Στον",
    "Στη",
    "Στην",
    "Στους",
    "Στις",
    "Σε",
    "Για",
    "Όλοι",
    "Όλα",
    "Όλες",
    "Ένας",
    "Μία",
    "Μια",
    "Ένα",
    "Με",
    "Όταν",
    "Από",
    "Αν",
)

_OPENERS_CLASS = r"«“\(\[\{‹⟨"

_SENTENCE_STARTERS_ALT: Final[str] = "|".join(re.escape(w) for w in SENTENCE_STARTERS_WORDS)

SENTENCE_STARTERS_RX: Final[re.Pattern[str]] = re.compile(
    rf"(?<![{_OPENERS_CLASS}])\b(?:{_SENTENCE_STARTERS_ALT})\b",
    re.UNICODE,
)

# Standalone short capitalized noun phrase (no sentence end)
CAPITALIZED_NOUN_ONLY_RX: Final[re.Pattern[str]] = re.compile(
    rf"^\s*([{_UPPERCLASS}][^.!?…]{{1,80}})\s*$",
    re.UNICODE,
)

# Boundary set for splitting title on starters (space/NBSP/newline/punct)
BOUNDARY_CHARS: Final[set[str]] = set(
    " \t\r\n"
    "\u00a0\u202f\u2007"
    "\u2002\u2003\u2004\u2005\u2006\u2008\u2009\u200a"
    ":;,.·»«\"'“”΄’`´-"
)


def _is_boundary_char(ch: str) -> bool:
    return ch in BOUNDARY_CHARS


# --- Dotted acronym detection (e.g., Α.Ε.Π.Ε.Υ., Π.Δ., Κ.Υ.Α.) --------------
_DOTTED_ACRONYM_CORE = rf"(?:[{_UPPERCLASS}]\.){{2,}}[{_UPPERCLASS}]?\.?"
DOTTED_ACRONYM_RX: Final[re.Pattern[str]] = re.compile(rf"^{_DOTTED_ACRONYM_CORE}$", re.UNICODE)

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

_WORD_RX = re.compile(r"[0-9A-Za-zΑ-ΩΆ-Ώα-ωά-ώϊΐϋΰ]+", re.UNICODE)
_CONNECTOR_SET = {w.casefold() for w in CONNECTOR_WORDS}


def _ends_with_connector_token(s: str) -> bool:
    m = re.search(r"[0-9A-Za-zΑ-ΩΆ-Ώα-ωά-ώϊΐϋΰ]+" + _WS_END + r"$", s, flags=re.UNICODE)
    return bool(m and m.group(0).strip().casefold().rstrip("\u200b\u2060\ufeff") in _CONNECTOR_SET)


def _strip_trailing_connector_token(s: str) -> str:
    m = re.search(r"^(.*?)([0-9A-Za-zΑ-ΩΆ-Ώα-ωά-ώϊΐϋΰ]+)" + _WS_END + r"$", s, flags=re.UNICODE)
    if m and m.group(2).strip().casefold() in _CONNECTOR_SET:
        return m.group(1).rstrip(" ,·—–-")
    return s


def _first_p_and_rest(html: str) -> tuple[str | None, str]:
    m = re.match(r"^\s*<p>(.*?)</p>\s*(.*)$", html, flags=re.DOTALL | re.UNICODE)
    if not m:
        return None, html
    return m.group(1), m.group(2)


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def _append_unique(title: str, frag: str) -> str:
    frag_s = (frag or "").strip()
    t = title or ""
    if frag_s and frag_s.casefold() not in t.casefold():
        if not t.endswith((" ", "(", "（")):
            t += " "
        t += frag_s
    return t


def _strip_trailing_connector(s: str) -> str:
    s2 = CONNECTOR_TRAILING_RX.sub("", s).rstrip(" ,·—–-")
    return s2 if s2 != s else _strip_trailing_connector_token(s)


def _append_with_connector_merge(title: str, frag: str) -> str:
    base = _strip_trailing_connector(title or "")
    frag_s = (frag or "").strip()
    if not frag_s:
        return base
    if frag_s.casefold() in base.casefold():
        return base
    return (base + " " + frag_s).strip()


def _word_count(s: str) -> int:
    return len(re.findall(r"[0-9A-Za-zΑ-ΩΆ-Ώα-ωά-ώϊΐϋΰ]+", s))


def _next_text_starts_with_starter(rest_html: str) -> bool:
    m = re.match(r"^\s*<p>(.*?)</p>", rest_html, flags=re.DOTALL | re.UNICODE)
    if m:
        txt = _strip_tags(m.group(1))
        return bool(SENTENCE_STARTERS_RX.match(txt))
    if re.match(r"^\s*<\s*(?:ul|ol)\b", rest_html, flags=re.IGNORECASE):
        return True
    m2 = re.match(r"^\s*<li>(.*?)</li>", rest_html, flags=re.DOTALL | re.UNICODE)
    if m2:
        txt = _strip_tags(m2.group(1))
        return bool(SENTENCE_STARTERS_RX.match(txt))
    return False


def _first_p_starts_with_starter(html: str) -> bool:
    first, _ = _first_p_and_rest(html)
    if first is None:
        return False
    return bool(SENTENCE_STARTERS_RX.match(_strip_tags(first)))


# ---------------------------------------------------------------------------
# Title pre-split on *any* sentence starter
# ---------------------------------------------------------------------------


def _split_on_sentence_starter_in_candidate(candidate: str, html: str) -> tuple[str, str]:
    cand = candidate or ""
    best_idx: int | None = None

    for w in SENTENCE_STARTERS_WORDS:
        for m in re.finditer(rf"(?<!\w){re.escape(w)}\b", cand, flags=re.UNICODE):
            i = m.start()
            if i == 0:
                continue
            prev = cand[i - 1]
            if not _is_boundary_char(prev):
                continue
            if best_idx is None or i < best_idx:
                best_idx = i

    if best_idx is None:
        return candidate, html

    left = cand[:best_idx].rstrip(" ,·—–-:").strip()
    right = cand[best_idx:].strip()

    if not left or len(left) > 60:
        return candidate, html
    if _word_count(right) < 3:
        return candidate, html

    new_html = f"<p>{right}</p>" + (html if html else "")
    return left, new_html


# ---------------------------------------------------------------------------
# Greek enum/list label handling inside the candidate title
# ---------------------------------------------------------------------------

_ENUM_SEQ: Final[tuple[str, ...]] = (
    "Α",
    "Β",
    "Γ",
    "Δ",
    "Ε",
    "Ζ",
    "Η",
    "Θ",
    "Ι",
    "Κ",
    "Λ",
    "Μ",
)
ENUM_LABEL_RX: Final[re.Pattern[str]] = re.compile(
    rf"(?<!\w)({'|'.join(_ENUM_SEQ)})\.\s+(?=[{_UPPERCLASS}])",
    re.UNICODE,
)


def _article_prefix_end_index(cand: str, num: int) -> int:
    m = re.search(
        rf"\bΆρθρο\s+{re.escape(str(num))}\b\s*[:\-–—]?\s*",
        cand,
        flags=re.UNICODE | re.IGNORECASE,
    )
    return m.end() if m else 0


def _strip_leading_article_prefix(num: int, s: str) -> str:
    return re.sub(
        rf"^\s*Άρθρο\s+{re.escape(str(num))}\s*[:\-–—]\s*",
        "",
        s,
        flags=re.UNICODE | re.IGNORECASE,
    )


def _has_all_prior_enum_labels(cand: str, start_idx: int, pos: int, label: str) -> bool:
    try:
        idx = _ENUM_SEQ.index(label)
    except ValueError:
        return False
    if idx == 0:
        return True
    window = cand[start_idx:pos]
    for prior in _ENUM_SEQ[:idx]:
        if not re.search(
            rf"(?<!\w){re.escape(prior)}\.\s+(?=[{_UPPERCLASS}])", window, flags=re.UNICODE
        ):
            return False
    return True


def _split_on_enum_label_in_candidate(candidate: str, html: str, num: int) -> tuple[str, str]:
    cand = candidate or ""
    matches = list(ENUM_LABEL_RX.finditer(cand))
    if not matches:
        return candidate, html

    prefix_end = _article_prefix_end_index(cand, num)

    pick = None
    for m in matches:
        label = m.group(1)
        if _has_all_prior_enum_labels(cand, prefix_end, m.start(), label):
            pick = m
            break

    if not pick:
        return candidate, html

    left = cand[: pick.start()].rstrip(" ,·—–-:").strip()
    right = cand[pick.start() :].strip()

    if not left or _word_count(right) < 2:
        return candidate, html

    new_html = f"<p>{right}</p>" + (html or "")
    return left, new_html


# --- Final guard (push): move any leftover enum clause from title into body --


def _push_any_enum_clause_to_body(candidate: str, html: str, num: int) -> tuple[str, str]:
    cand = candidate or ""
    if not cand:
        return candidate, html

    prefix_end = _article_prefix_end_index(cand, num)
    pick = None
    for m in ENUM_LABEL_RX.finditer(cand):
        label = m.group(1)
        if _has_all_prior_enum_labels(cand, prefix_end, m.start(), label):
            pick = m
            break
    if not pick:
        return candidate, html

    left = cand[: pick.start()].rstrip(" ,·—–-:").strip()
    right = cand[pick.start() :].strip()

    if not left:
        return candidate, html

    first_p, _ = _first_p_and_rest(html)
    right_norm = right.strip().casefold()
    if first_p is not None and _strip_tags(first_p).strip().casefold() == right_norm:
        new_html = html
    else:
        new_html = f"<p>{right}</p>" + (html or "")

    return left, new_html


# ---------------------------------------------------------------------------
# Split in-body paragraphs on enum labels (Α., Β., Γ., …)
# ---------------------------------------------------------------------------


def _split_p_text_on_enum_labels(txt: str) -> list[str]:
    if not txt:
        return [txt]
    positions: list[int] = []
    anchor = 0
    for m in ENUM_LABEL_RX.finditer(txt):
        label = m.group(1)
        try:
            idx = _ENUM_SEQ.index(label)
        except ValueError:
            continue
        if idx == 0:
            positions.append(m.start())
            anchor = m.start()
            continue
        window = txt[anchor : m.start()]
        ok = True
        for prior in _ENUM_SEQ[:idx]:
            if not re.search(
                rf"(?<!\w){re.escape(prior)}\.\s+(?=[{_UPPERCLASS}])", window, flags=re.UNICODE
            ):
                ok = False
                break
        if ok:
            positions.append(m.start())
    if not positions:
        return [txt]
    chunks: list[str] = []
    pre = txt[: positions[0]].strip()
    if pre:
        chunks.append(pre)
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(txt)
        frag = txt[start:end].strip()
        if frag:
            chunks.append(frag)
    return chunks


def _split_enum_labels_inside_paragraphs(html: str) -> str:
    def _repl(m: re.Match[str]) -> str:
        inner = m.group(1)
        chunks = _split_p_text_on_enum_labels(inner)
        if len(chunks) <= 1:
            return m.group(0)
        return "".join(f"<p>{c}</p>" for c in chunks)

    return re.sub(r"(?s)<p>(.*?)</p>", _repl, html, flags=re.DOTALL | re.UNICODE)


# ---------------------------------------------------------------------------
# Extract enum labels from lists into standalone <p> after the list
# ---------------------------------------------------------------------------


def _has_all_prior_enum_labels_in_html(full_html: str, pos: int, label: str) -> bool:
    try:
        idx = _ENUM_SEQ.index(label)
    except ValueError:
        return False
    if idx == 0:
        return True
    window = full_html[:pos]
    for prior in _ENUM_SEQ[:idx]:
        if not re.search(
            rf"(?<!\w){re.escape(prior)}\.\s+(?=[{_UPPERCLASS}])", window, flags=re.UNICODE
        ):
            return False
    return True


def _extract_enum_labels_from_lists(html: str) -> str:
    out: list[str] = []
    last_end = 0
    list_block_rx = re.compile(r"(?s)<(ul|ol)>(.*?)</\1>", re.UNICODE)
    li_rx = re.compile(r"(?s)<li>(.*?)</li>", re.UNICODE)

    for ulm in list_block_rx.finditer(html):
        out.append(html[last_end : ulm.start()])
        tag = ulm.group(1)
        inner = ulm.group(2)
        open_len = len(f"<{tag}>")
        inner_global_start = ulm.start() + open_len

        li_out_parts: list[str] = []
        li_last_end = 0
        after_paras: list[str] = []

        for lim in li_rx.finditer(inner):
            li_out_parts.append(inner[li_last_end : lim.start()])

            li_inner = lim.group(1)
            li_inner_global_start = inner_global_start + lim.start() + len("<li>")

            valid_starts: list[int] = []
            for m in ENUM_LABEL_RX.finditer(li_inner):
                label = m.group(1)
                global_pos = li_inner_global_start + m.start()
                if _has_all_prior_enum_labels_in_html(html, global_pos, label):
                    valid_starts.append(m.start())

            if not valid_starts:
                li_out_parts.append(f"<li>{li_inner}</li>")
            else:
                pre = li_inner[: valid_starts[0]].strip()
                if pre:
                    li_out_parts.append(f"<li>{pre}</li>")
                for i, start in enumerate(valid_starts):
                    end = valid_starts[i + 1] if i + 1 < len(valid_starts) else len(li_inner)
                    chunk = li_inner[start:end].strip()
                    if chunk:
                        after_paras.append(f"<p>{chunk}</p>")

            li_last_end = lim.end()

        li_out_parts.append(inner[li_last_end:])
        new_inner = "".join(li_out_parts)
        out.append(f"<{tag}>{new_inner}</{tag}>")
        out.append("".join(after_paras))

        last_end = ulm.end()

    out.append(html[last_end:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Demote candidate when body starts with a number (continuation like "… του άρθρου 6 …")
# ---------------------------------------------------------------------------

_NUMBER_START_RX: Final[re.Pattern[str]] = re.compile(r'^[«“"\']*\s*[\(\[]*\s*\d', re.UNICODE)


def _remove_first_li_from_first_list(html: str) -> tuple[str, str | None]:
    list_block_rx = re.compile(r"(?s)<(ul|ol)>(.*?)</\1>", re.UNICODE | re.IGNORECASE)
    li_rx = re.compile(r"(?s)<li>(.*?)</li>", re.UNICODE | re.IGNORECASE)

    m = list_block_rx.search(html or "")
    if not m:
        return html, None
    tag, inner = m.group(1), m.group(2)

    mli = li_rx.search(inner)
    if not mli:
        return html, None

    li_text = mli.group(1)
    new_inner = inner[: mli.start()] + inner[mli.end() :]
    new_block = f"<{tag}>{new_inner}</{tag}>" if li_rx.search(new_inner) else ""
    new_html = html[: m.start()] + new_block + html[m.end() :]
    return new_html, li_text


def _demote_when_body_starts_numeric_continuation(candidate: str, html: str) -> tuple[str, str]:
    cand = (candidate or "").strip()
    if not cand:
        return candidate, html

    first_p, rest = _first_p_and_rest(html or "")
    if first_p is not None:
        txt = _strip_tags(first_p)
        if _NUMBER_START_RX.match(txt or ""):
            merged = f"<p>{cand} {txt}</p>"
            return "", merged + rest

    if re.match(r"^\s*<\s*(?:ul|ol)\b", html or "", flags=re.IGNORECASE):
        new_html, first_li_text = _remove_first_li_from_first_list(html or "")
        if first_li_text is not None:
            li_txt = _strip_tags(first_li_text).strip()
            if _NUMBER_START_RX.match(li_txt or ""):
                merged = f"<p>{cand} {li_txt}</p>"
                return "", merged + new_html

    return candidate, html


# ---------------------------------------------------------------------------
# NEW: Detect & demote if candidate is / contains a (possibly truncated) sentence
# ---------------------------------------------------------------------------

# sentence boundary inside a string: sentence end + space + Uppercase start
_SENTENCE_INTERNAL_BOUNDARY_RX: Final[re.Pattern[str]] = re.compile(
    rf"[.!;!?…]\s+(?=[{_UPPERCLASS}])",
    re.UNICODE,
)

# lightweight verb ending heuristic for Greek (covers -ει, -ουν, -ται, -νται κ.ά.)
_VERB_ENDING_RX: Final[re.Pattern[str]] = re.compile(
    r"(?:[A-Za-zΑ-ΩΆ-Ώα-ωάέήίόύώϊΐϋΰ]+"
    r"(?:ει|εί|εις|ουμε|ούμε|ουν|ούν|"
    r"εται|ται|ονται|νται|"
    r"ήθηκε|ήθηκαν|ησε|ησαν|"
    r"ήσει|ήσεις|είναι|ήταν|πρέπει|γίνεται))\b",
    re.IGNORECASE | re.UNICODE,
)


def _is_complete_sentence(s: str) -> bool:
    """
    Heuristic: πρόταση που αρχίζει με κεφαλαίο (αγνοώντας εισαγωγικά),
    περιέχει τουλάχιστον ένα 'ρήμα' (κατάληξη), και τελειώνει σε τελεία/;!/…
    """
    s = (s or "").strip()
    if not s:
        return False

    # Strip leading quotes/brackets
    s = re.sub(r'^[«“"\'(\[]+\s*', "", s)

    # must end with sentence punctuation
    if not END_PUNCT_RX.search(s):
        return False

    # must start with uppercase (Greek/Latin)
    if not re.match(rf"^[{_UPPERCLASS}]", s, flags=re.UNICODE):
        return False

    # must contain a word with a common Greek verb ending
    return bool(_VERB_ENDING_RX.search(s))


_STRUCTURAL_TOKENS_RX: Final[re.Pattern[str]] = re.compile(
    r"\b(ΜΕΡΟΣ|ΚΕΦΑΛΑΙΟ|ΤΜΗΜΑ)\b", re.UNICODE
)


def _demote_if_complete_sentence(candidate: str, html: str) -> tuple[str, str]:
    """
    Αν ο υποψήφιος τίτλος είναι *ή περιέχει* πλήρη πρόταση, κάνε demote ΟΛΟ τον τίτλο
    στο σώμα ως <p>…</p>. Αυτό καλύπτει περιπτώσεις όπως του Άρθρου 99.
    """
    cand = (candidate or "").strip()
    if not cand:
        return candidate, html

    # whole candidate is a sentence?
    if _is_complete_sentence(cand):
        return "", f"<p>{cand}</p>" + (html or "")

    # contains a sentence inside? (terminal punctuation + space + uppercase)
    m = _SENTENCE_INTERNAL_BOUNDARY_RX.search(cand)
    if m:
        left = cand[: m.start() + 1].strip()  # include punctuation
        if _is_complete_sentence(left):
            return "", f"<p>{cand}</p>" + (html or "")

    # structural tokens after a dot → demote
    if "." in cand and _STRUCTURAL_TOKENS_RX.search(cand):
        return "", f"<p>{cand}</p>" + (html or "")

    return candidate, html


# ---------------------------------------------------------------------------
# Dotted acronym tail de-dup (e.g., title ends with " … Α.Ε.Π.Ε.Υ.")
# ---------------------------------------------------------------------------

TRAILING_DOTTED_ACRONYM_RX: Final[re.Pattern[str]] = re.compile(
    rf"\s+({_DOTTED_ACRONYM_CORE}){_WS_END}$", re.UNICODE
)


def _first_list_item_text(html: str) -> str | None:
    m = re.match(
        r"^\s*<\s*(?:ul|ol)\b[^>]*>\s*<li>(.*?)</li>", html or "", flags=re.DOTALL | re.IGNORECASE
    )
    if not m:
        return None
    return _strip_tags(m.group(1)).strip() or None


def _strip_trailing_dotted_acronym_if_dup(candidate: str, html: str) -> tuple[str, str]:
    cand = candidate or ""
    m = TRAILING_DOTTED_ACRONYM_RX.search(cand)
    if not m:
        return candidate, html

    acro = (m.group(1) or "").strip()

    first_p, _ = _first_p_and_rest(html or "")
    if first_p and _strip_tags(first_p).strip() == acro:
        new_title = cand[: m.start()].rstrip(" ,·—–-")
        return new_title, html

    li_txt = _first_list_item_text(html or "")
    if li_txt and li_txt == acro:
        new_title = cand[: m.start()].rstrip(" ,·—–-")
        return new_title, html

    return candidate, html


# ---------------------------------------------------------------------------
# Individual fixups
# ---------------------------------------------------------------------------


def pull_directive_parenthetical_into_title(title: str, html: str) -> tuple[str, str]:
    first, rest = _first_p_and_rest(html)
    if first is None:
        return title, html
    txt = _strip_tags(first)
    if not DIRECTIVE_PAREN_RX.match(txt):
        return title, html
    inner = txt[1:-1].strip() if txt.startswith("(") and txt.endswith(")") else txt
    title2 = _append_unique(title, f"({inner})")
    return title2, rest.lstrip()


def pull_leading_lowercase_phrase_from_first_p(title: str, html: str) -> tuple[str, str]:
    first, rest = _first_p_and_rest(html)
    if first is None:
        return title, html
    txt = _strip_tags(first)
    if not txt or SENTENCE_STARTERS_RX.match(txt):
        return title, html
    m = LEADING_LOWER_FRAGMENT_RX.match(txt)
    if not m:
        return title, html
    frag = m.group(1).strip()
    remainder = m.group(2).strip()
    title2 = _append_unique(title, frag)
    new_first_p = f"<p>{remainder}</p>" if remainder else ""
    return title2, (new_first_p + rest).lstrip()


def _consume_prefix_until_starter(html: str) -> tuple[str, str]:
    remaining = html
    acc: list[str] = []
    while True:
        m_p = re.match(r"^\s*<p>(.*?)</p>\s*(.*)$", remaining, flags=re.DOTALL | re.UNICODE)
        if m_p:
            ptxt = _strip_tags(m_p.group(1)).strip()
            rest = m_p.group(2)
            if not ptxt:
                remaining = rest
                continue
            m_start = SENTENCE_STARTERS_RX.search(ptxt)
            if m_start:
                if m_start.start() == 0:
                    return (" ".join(acc).strip(), remaining)
                acc.append(ptxt[: m_start.start()].strip())
                leftover = ptxt[m_start.start() :].strip()
                new_first_p = f"<p>{leftover}</p>" if leftover else ""
                new_html = new_first_p + rest
                return (" ".join(acc).strip(), new_html)
            if END_PUNCT_RX.search(ptxt):
                return (" ".join(acc).strip(), remaining)
            acc.append(ptxt)
            remaining = rest
            continue
        if re.match(r"^\s*<\s*(?:ul|ol)\b", remaining, flags=re.IGNORECASE):
            return (" ".join(acc).strip(), remaining)
        return (" ".join(acc).strip(), remaining)


def pull_paragraph_after_connector_into_title(title: str, html: str) -> tuple[str, str]:
    prefix, rest_html = _consume_prefix_until_starter(html)

    if not prefix:
        return title, html
    m = TRAILING_COLON_CLAUSE_RX.match(prefix or "")
    if m:
        return title, html
    new_title = _append_with_connector_merge(title, prefix)
    return new_title, rest_html.lstrip()


def pull_standalone_capitalized_p_into_title(title: str, html: str) -> tuple[str, str]:
    """
    If the first <p> is a short capitalized noun phrase or a dotted acronym
    and the *next* chunk clearly starts the body (sentence starter or list),
    that phrase belongs to the title. We only APPEND/MERGE (no replace).
    """
    first, rest = _first_p_and_rest(html)
    if first is None:
        return title, html
    frag = _strip_tags(first).strip()
    if not frag:
        return title, html

    is_capitalized_noun = bool(CAPITALIZED_NOUN_ONLY_RX.match(frag))
    is_dotted_acronym = bool(DOTTED_ACRONYM_RX.match(frag))
    if is_dotted_acronym and len(frag) > 20:
        is_dotted_acronym = False

    if not (is_capitalized_noun or is_dotted_acronym):
        return title, html
    if not _next_text_starts_with_starter(rest):
        return title, html
    if frag.casefold() in (title or "").casefold():
        return title, rest.lstrip()

    title2 = (
        _append_with_connector_merge(title, frag)
        if CONNECTOR_TRAILING_RX.search(title)
        else _append_unique(title, frag)
    )
    return title2, rest.lstrip()


def pull_lowercase_continuation_into_title(title: str, html: str) -> tuple[str, str]:
    first, rest = _first_p_and_rest(html)
    if first is None:
        return title, html
    txt = _strip_tags(first)
    if SENTENCE_STARTERS_RX.match(txt):
        return title, html
    if not txt or len(txt) > 80:
        return title, html
    if re.search(r"[.!;!?…]$", txt):
        return title, html
    if not LOWERCASE_START_RX.match(txt):
        return title, html
    if txt.casefold() in title.casefold():
        return title, rest.lstrip()
    title2 = _append_unique(title, txt)
    return title2, rest.lstrip()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def finalize_title(num: int, candidate: str) -> str:
    clean = (candidate or "").strip(" ,·—–-")
    clean = re.sub(r"\s*\(", " (", clean)
    return f"Άρθρο {num}" + (f": {clean}" if clean else "")


def _strip_invisible_end_spaces(s: str) -> str:
    return re.sub(r"[\u200b\u2060\ufeff]+", "", s)


def apply_title_body_fixups(num: int, title: str, html: str) -> tuple[str, str]:
    # 0) normalize & early demotions
    title = _strip_invisible_end_spaces(title)
    title = _strip_leading_article_prefix(num, title)

    # Demote if body starts with a numeric continuation
    title, html = _demote_when_body_starts_numeric_continuation(title, html)

    # 1) split on starters inside candidate title
    t_core, h = _split_on_sentence_starter_in_candidate(title, html)

    # 1b) split on Greek list/section label inside candidate title
    t_core, h = _split_on_enum_label_in_candidate(t_core, h, num)

    # 2) directive parenthesis
    t_core, h = pull_directive_parenthetical_into_title(t_core, h)

    # 3) connector-aware merges
    t_core, h = pull_paragraph_after_connector_into_title(t_core, h)

    # Demote if the candidate is / contains a (possibly truncated) sentence (e.g. Article 99)
    t_core, h = _demote_if_complete_sentence(t_core, h)

    # 4) gate
    if _first_p_starts_with_starter(h):
        t_core, h = _push_any_enum_clause_to_body(t_core, h, num)
        h = _extract_enum_labels_from_lists(h)
        h = _split_enum_labels_inside_paragraphs(h)
        t_core, h = _strip_trailing_dotted_acronym_if_dup(t_core, h)
        return finalize_title(num, t_core), h

    # 5) remaining pulls
    t_core, h = pull_leading_lowercase_phrase_from_first_p(t_core, h)
    t_core, h = pull_standalone_capitalized_p_into_title(t_core, h)
    t_core, h = pull_lowercase_continuation_into_title(t_core, h)

    # 6) final guard + body normalization
    t_core, h = _push_any_enum_clause_to_body(t_core, h, num)
    h = _extract_enum_labels_from_lists(h)
    h = _split_enum_labels_inside_paragraphs(h)
    t_core, h = _strip_trailing_dotted_acronym_if_dup(t_core, h)

    return finalize_title(num, t_core), h
