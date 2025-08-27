from fek_extractor.parsing.normalize import (
    dehyphenate_lines,
    dehyphenate_text,
    fix_soft_hyphens_inline,
    normalize_text,
)


def test_fix_soft_hyphens_inline():
    s = "Αποφ\u00adάσεις και δοκ\u00adιμές"
    assert fix_soft_hyphens_inline(s) == "Αποφάσεις και δοκιμές"


def test_dehyphenate_lines_wrap():
    # In real PDFs, the accent is preserved on the first chunk: "μεγά-" + "λο"
    lines = ["Αυτό είναι ένα μεγά-", "λο κείμενο."]
    out = dehyphenate_lines(lines)
    assert out == ["Αυτό είναι ένα μεγάλο κείμενο."]


def test_dehyphenate_lines_no_join_on_uppercase():
    lines = ["κάποιο-", "Κείμενο"]
    out = dehyphenate_lines(lines)
    # should not join because next starts uppercase
    assert out == lines


def test_dehyphenate_text_roundtrip():
    raw = "Πολύ-\nωραίο κείμενο."
    assert dehyphenate_text(raw) == "Πολύωραίο κείμενο."


def test_normalize_text_keeps_hard_hyphen_but_drops_soft():
    s = "δοκ-ιμή και δοκ\u00adιμή"
    n = normalize_text(s)
    assert "δοκ-ιμή" in n
    assert "δοκ\u00adιμή" not in n
