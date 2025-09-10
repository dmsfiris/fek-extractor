# tests/unit/test_normalize.py
from fek_extractor.parsing.normalize import (
    dehyphenate_lines,
    dehyphenate_text,
    normalize_text,
)


def test_normalize_text() -> None:
    s = " A\u00a0test\nwith\tmulti\tspace &amp; entities "
    assert normalize_text(s) == "A test with multi space & entities"


def test_dehyphenate_text_newline_join() -> None:
    # εφαρμόζο-\nνται => εφαρμόζονται
    s = "Αυτό δεν εφαρμόζο-\nνται συχνά."
    assert dehyphenate_text(s) == "Αυτό δεν εφαρμόζονται συχνά."


def test_dehyphenate_text_space_join() -> None:
    # επο-   πτικών => εποπτικών
    s = "στο πλαίσιο των επο-   πτικών αρμοδιοτήτων"
    assert dehyphenate_text(s) == "στο πλαίσιο των εποπτικών αρμοδιοτήτων"


def test_dehyphenate_text_preserves_real_hyphens() -> None:
    # Should not touch true hyphens with uppercase names
    s = "ΣΠΥΡΙΔΩΝ - ΑΔΩΝΙΣ"
    assert dehyphenate_text(s) == "ΣΠΥΡΙΔΩΝ - ΑΔΩΝΙΣ"


def test_dehyphenate_text_restores_accent() -> None:
    # μεγα-\nλο => μεγάλο
    s = "Αυτό είναι ένα μεγά-\nλο παράδειγμα."
    assert dehyphenate_text(s) == "Αυτό είναι ένα μεγάλο παράδειγμα."


def test_dehyphenate_lines_basic() -> None:
    lines = ["Αυτό είναι ένα μεγά-", "λο κείμενο."]
    out = dehyphenate_lines(lines)
    assert out == ["Αυτό είναι ένα μεγάλο κείμενο."]


def test_dehyphenate_text_soft_hyphen_with_spaces() -> None:
    # Handle soft hyphen + spaces: "διοικη\u00AD  τικό" => "διοικητικό"
    s = "Το πλαίσιο είναι διοικη\u00ad  τικό και σαφές."
    assert dehyphenate_text(s) == "Το πλαίσιο είναι διοικητικό και σαφές."


def test_dehyphenate_text_idempotent() -> None:
    s = "εφαρμόζο-\nνται επο-  πτικών"
    once = dehyphenate_text(s)
    twice = dehyphenate_text(once)
    assert once == twice
