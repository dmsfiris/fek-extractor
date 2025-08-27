from __future__ import annotations

from fek_extractor.parsing.authority import find_issuing_authorities

LINES = [
    "ΕΦΗΜΕΡΙΔΑ ΤΗΣ ΚΥΒΕΡΝΗΣΕΩΣ",
    "ΤΗΣ ΕΛΛΗΝΙΚΗΣ ΔΗΜΟΚΡΑΤΙΑΣ",
    "Βουλή των Ελλήνων",
    "ΝΟΜΟΣ ΥΠ’ ΑΡΙΘ. 4706",
    "",
    "Υπουργείο Οικονομικών",
    "Γενική Γραμματεία Δημοσιονομικής Πολιτικής",
    "ΑΠΟΦΑΣΗ",
    "Κείμενο...",
]


def test_find_issuing_authorities_basic():
    out = find_issuing_authorities(LINES, head_scan=20)
    # should capture Βουλή + Υπουργείο (order preserved, trimmed)
    assert out[0].lower().startswith("βουλή") or out[0].lower().startswith("βουλη")
    assert any("Υπουργείο" in x or "Υπουργειο" in x for x in out)
    assert len(out) <= 3
