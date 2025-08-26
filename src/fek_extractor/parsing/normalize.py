from __future__ import annotations

import html as htmlmod
import re
import unicodedata


def normalize_text(s: str) -> str:
    """Normalize Unicode, unescape HTML entities, and collapse whitespace."""
    s = htmlmod.unescape(s)
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[\s\u00A0]+", " ", s).strip()
    return s
