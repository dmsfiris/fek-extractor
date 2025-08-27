from __future__ import annotations

import re

# Example headers:
#   ΦΕΚ Α 123/01.01.2024
#   ΦΕΚ Β 987/1-1-24
#   ΦΕΚ Α’ 12/1/2024
FEK_HEADER_RX = re.compile(
    r"(?i)ΦΕΚ\s*(?P<series>[Α-ΩA-Z])\s*[’']?\s*(?P<number>\d+)\s*/\s*(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
    re.UNICODE,
)

# Decision id:
#   Αριθ. 12345   /  Αριθ 123/Β/2024   /  Αριθμ. ΔΥΓ2/1234
DECISION_NO_RX = re.compile(
    r"(?i)\bΑριθ(?:\.|μ\.)?\s*(?P<decision>[A-Za-zΑ-Ωα-ω0-9/_\-.]+)",
    re.UNICODE,
)

# Subject (ONE LINE ONLY): "ΘΕΜΑ: ...."
SUBJECT_LINE_RX = re.compile(
    r"(?im)^\s*Θ[έε]μα\s*[:：]\s*(?P<subject>[^\r\n]+)",
    re.UNICODE,
)
