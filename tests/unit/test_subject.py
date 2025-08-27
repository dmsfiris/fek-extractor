from __future__ import annotations

from fek_extractor.parsing.subject import extract_subject


def test_subject_single_line():
    lines = [
        "Αριθ. 4567",
        "ΘΕΜΑ: Ρύθμιση διαδικασιών για το Χ.",
        "Κυρίως κείμενο ξεκινά...",
    ]
    subj = extract_subject(lines)
    assert subj == "Ρύθμιση διαδικασιών για το Χ."


def test_subject_multiline_until_blank():
    lines = [
        "ΦΕΚ Α 123/01.01.2024",
        "Αριθ. 4567",
        "ΘΕΜΑ: Δοκιμή θέματος με δεύτερη γραμμή",
        "συνέχεια θέματος εδώ.",
        "",
        "Κυρίως κείμενο...",
    ]
    subj = extract_subject(lines)
    assert subj is not None
    assert "Δοκιμή θέματος" in subj
    assert "δεύτερη γραμμή" in subj
    assert "συνέχεια θέματος εδώ" in subj
    assert "Κυρίως κείμενο" not in subj


def test_subject_stops_at_article_head():
    lines = [
        "Θέμα - Ρυθμίσεις προληπτικές",
        "και διαδικαστικές διατάξεις",
        "Άρθρο 1",
        "Τίτλος",
    ]
    subj = extract_subject(lines)
    assert subj == "Ρυθμίσεις προληπτικές και διαδικαστικές διατάξεις"
