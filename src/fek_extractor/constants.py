# src/fek_extractor/constants.py
from __future__ import annotations

import re
from typing import Final

# Bump when the JSON structure or field semantics change
SCHEMA_VERSION: Final = "0.4.0"

# ---------------------------------------------------------------------------
# FEK header / masthead
# Examples this matches (case-insensitive):
#   "ΦΕΚ Α 123/01.01.2024"
#   "ΦΕΚ Β 4567/1.6.2023"
# (headers.py may join wrapped lines like "ΦΕΚ Α 123/01.01." + "2024")
# ---------------------------------------------------------------------------
FEK_HEADER_RX: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bΦΕΚ\s+(?P<series>[Α-ΩA-ZΆΈΉΊΌΎΏ])\s+"
    r"(?P<number>\d+)\s*/\s*(?P<date>\d{1,2}\.\d{1,2}\.\d{2,4})"
)

# Common D.M.YY(YY) date pattern with dots, used by various helpers
DATE_DMY_DOTS_RX: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})\b"
)

# "Αριθ." decision number lines (tolerant to variants). Useful in text parsing.
DECISION_NO_RX: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*(?:Αριθ\.?|Αριθμ\.?)\s*(?P<decision>[^\s].*)$"
)

# Subject headline starter (ΘΕΜΑ / Θέμα), kept here for reuse if needed.
SUBJECT_LINE_RX: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*Θ[ΕEΈέ]ΜΑ\b\s*[:\-–—]?\s*(?P<body>.*)$"
)
