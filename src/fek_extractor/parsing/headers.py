from __future__ import annotations

import re
from typing import Final

from ..constants import FEK_HEADER_RX
from .normalize import normalize_text

# Private, module-scoped helpers (not part of the public API)
_DATE_SUFFIX_RE: Final = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\s*$")
_YEAR_PREFIX_RE: Final = re.compile(r"^\d{2,4}\b")


def _smart_join(left: str, right: str) -> str:
    """Join two lines; if left ends with a date separator and right starts with digits,
    join without an extra space (handles '01.01.' + '2024'). Otherwise join with one space.
    """
    left_trim = left.rstrip()
    right_trim = right.lstrip()
    if _DATE_SUFFIX_RE.search(left_trim) and _YEAR_PREFIX_RE.match(right_trim):
        return left_trim + right_trim  # tight join for date continuation
    return f"{left_trim} {right_trim}"


def find_fek_header_line(lines: list[str]) -> str | None:
    """Return the first line (or joined pair) that matches a ΦΕΚ header."""
    # check first ~10 lines (typical masthead area)
    for line in lines[:10]:
        if FEK_HEADER_RX.search(line):
            return line

    # try joining adjacent lines (headers sometimes wrap)
    limit = min(10, len(lines) - 1)
    for i in range(limit):
        joined = normalize_text(_smart_join(lines[i], lines[i + 1]))
        if FEK_HEADER_RX.search(joined):
            return joined

    return None


def parse_fek_header(s: str) -> dict[str, str]:
    """Extract fields from a ΦΕΚ header string."""
    out: dict[str, str] = {}
    m = FEK_HEADER_RX.search(s)
    if not m:
        return out
    out["fek_series"] = m.group("series")
    out["fek_number"] = m.group("number")
    out["fek_date"] = m.group("date")
    return out
