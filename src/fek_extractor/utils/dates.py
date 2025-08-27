from __future__ import annotations

from datetime import datetime

_SEP_CANDIDATES = [".", "/", "-"]
_FMT_CANDIDATES = [
    "%d{sep}%m{sep}%Y",
    "%d{sep}%m{sep}%y",
    "%d{sep}%m{sep}%Y ",  # tolerate trailing space
    "%d{sep}%m{sep}%y ",
]


def parse_date_to_iso(s: str) -> str | None:
    """Parse Greek day-first dates like 01.01.2024 / 1/1/24 -> 'YYYY-MM-DD'.
    Returns None if parsing fails.
    """
    s = s.strip()
    for sep in _SEP_CANDIDATES:
        for fmt in _FMT_CANDIDATES:
            try:
                dt = datetime.strptime(s, fmt.format(sep=sep))
                # handle 2-digit years conservatively (>=1970, else assume 2000s)
                year = dt.year
                if year < 100:
                    year += 2000 if year < 50 else 1900
                    dt = dt.replace(year=year)
                return dt.date().isoformat()
            except ValueError:
                continue
    return None
