from __future__ import annotations

from fek_extractor.parsing.signatures import find_signatories

LINES = [
    "ΚΥΡΙΩΣ ΚΕΙΜΕΝΟ ...",
    "Λήξη κειμένου.",
    "",
    "Ο Υπουργός Περιβάλλοντος και Ενέργειας",
    "ΓΕΩΡΓΙΟΣ ΠΑΠΑΔΟΠΟΥΛΟΣ",
    "",
    "Η Υπουργός Παιδείας και Θρησκευμάτων",
    "ΝΙΚΗ ΚΕΡΑΜΕΩΣ",
]


def test_find_signatories_basic():
    sigs = find_signatories(LINES, tail_scan=50)
    assert len(sigs) >= 2
    titles = [s["title"] for s in sigs]
    names = [s["name"] for s in sigs]
    assert any("Υπουργός" in t for t in titles)
    assert "ΓΕΩΡΓΙΟΣ ΠΑΠΑΔΟΠΟΥΛΟΣ" in names
    assert "ΝΙΚΗ ΚΕΡΑΜΕΩΣ" in names
