import re

from fek_extractor.parsing.html import lines_to_html


def _compact(s: str) -> str:
    """Collapse whitespace so HTML comparisons are resilient to formatting."""
    return re.sub(r"\s+", " ", (s or "").strip())


# -------------------------
# Paragraphs (FEK-style body lines)
# -------------------------


def test_paragraph_merge_and_flush_on_blank_line() -> None:
    # Typical continuous FEK paragraph across lines, then a blank-line flush.
    html = lines_to_html(["Προοίμιο τίτλου", "συνέχεια τίτλου.", "", "Νέα παράγραφος"])
    expected = "<p>Προοίμιο τίτλου συνέχεια τίτλου.</p><p>Νέα παράγραφος</p>"
    assert _compact(html) == _compact(expected)


# -------------------------
# Unordered markers (dash / dot)
# -------------------------


def test_simple_unordered_list_dash() -> None:
    html = lines_to_html(["- Πρώτο", "- Δεύτερο", "- Τρίτο"])
    expected = "<ul><li>Πρώτο</li><li>Δεύτερο</li><li>Τρίτο</li></ul>"
    assert _compact(html) == _compact(expected)


def test_bullet_dot_marker() -> None:
    html = lines_to_html(["• Α", "• Β"])
    expected = "<ul><li>Α</li><li>Β</li></ul>"
    assert _compact(html) == _compact(expected)


# -------------------------
# Ordered-like markers that FEK often uses
# (we intentionally render them as <ul> per your design)
# -------------------------


def test_numeric_dot_markers_render_as_ul() -> None:
    html = lines_to_html(["1. Α", "2. Β", "3. Γ"])
    expected = "<ul><li>Α</li><li>Β</li><li>Γ</li></ul>"
    assert _compact(html) == _compact(expected)


def test_numeric_paren_markers_render_as_ul() -> None:
    html = lines_to_html(["1) Α", "2) Β"])
    expected = "<ul><li>Α</li><li>Β</li></ul>"
    assert _compact(html) == _compact(expected)


def test_roman_markers_render_as_ul() -> None:
    html = lines_to_html(["i) Α", "ii) Β", "III) Γ"])
    expected = "<ul><li>Α</li><li>Β</li><li>Γ</li></ul>"
    assert _compact(html) == _compact(expected)


def test_greek_letter_markers_render_as_ul() -> None:
    html = lines_to_html(["α) Πρώτο", "β) Δεύτερο", "(γ) Τρίτο"])
    expected = "<ul><li>Πρώτο</li><li>Δεύτερο</li><li>Τρίτο</li></ul>"
    assert _compact(html) == _compact(expected)


# -------------------------
# Mixed paragraph + list (common FEK layout)
# -------------------------


def test_paragraph_then_list_then_paragraph_with_blank_line() -> None:
    # After the list, a blank line forces a new paragraph — common in FEK.
    lines = ["Εισαγωγή", "- Στοιχείο Α.", "- Στοιχείο Β.", "", "Κατακλείδα"]
    html = lines_to_html(lines)
    expected = (
        "<p>Εισαγωγή</p>" "<ul><li>Στοιχείο Α.</li><li>Στοιχείο Β.</li></ul>" "<p>Κατακλείδα</p>"
    )
    assert _compact(html) == _compact(expected)


def test_list_then_capitalized_line_is_new_paragraph() -> None:
    # Capitalized line after an open list → not a continuation; becomes <p>.
    lines = ["- Υποχρεώσεις.", "Η διαδικασία ολοκληρώνεται με απόφαση."]
    html = lines_to_html(lines)
    expected = "<ul><li>Υποχρεώσεις.</li></ul>" "<p>Η διαδικασία ολοκληρώνεται με απόφαση.</p>"
    assert _compact(html) == _compact(expected)


# -------------------------
# Continuations inside list items (FEK wording)
# -------------------------


def test_continuation_lowercase_merges_into_last_li() -> None:
    # Lowercase start → continuation of last <li>.
    lines = ["- Διατύπωση", "και συνέχεια σε νέα γραμμή."]
    html = lines_to_html(lines)
    expected = "<ul><li>Διατύπωση και συνέχεια σε νέα γραμμή.</li></ul>"
    assert _compact(html) == _compact(expected)


def test_continuation_parenthesis_merges_into_last_li() -> None:
    # Parenthesis start → continuation of last <li>.
    lines = ["- Ορισμός", "(βλ. σχετική απόφαση)"]
    html = lines_to_html(lines)
    expected = "<ul><li>Ορισμός (βλ. σχετική απόφαση)</li></ul>"
    assert _compact(html) == _compact(expected)


def test_continuation_punctuation_merges_into_last_li() -> None:
    # Punctuation start → continuation of last <li>.
    lines = ["- Γραμμή πρώτη,", "συνέχεια από κόμμα;", "και με ελληνικό ερωτηματικό;"]
    html = lines_to_html(lines)
    expected = "<ul><li>Γραμμή πρώτη, συνέχεια από κόμμα; και με ελληνικό ερωτηματικό;</li></ul>"
    assert _compact(html) == _compact(expected)


# -------------------------
# Nested lists under a parent that ends with “:”
# (very common in FEK articles, e.g. Article 23–style)
# -------------------------


def test_nested_under_colon_parent() -> None:
    # Parent line ends with “:”, then Greek-letter children.
    lines = [
        "- Τα χρηματοπιστωτικά μέσα ανήκουν στους πελάτες, εκτός εάν:",
        "α) έχει συσταθεί επ’ αυτών ενέχυρο,",
        "β) υφίσταται απαίτηση της ΑΕΠΕΥ κατά των δικαιούχων.",
    ]
    html = lines_to_html(lines)
    expected = (
        "<ul>"
        "<li>Τα χρηματοπιστωτικά μέσα ανήκουν στους πελάτες, εκτός εάν:"
        "<ul>"
        "<li>έχει συσταθεί επ’ αυτών ενέχυρο,</li>"
        "<li>υφίσταται απαίτηση της ΑΕΠΕΥ κατά των δικαιούχων.</li>"
        "</ul>"
        "</li>"
        "</ul>"
    )
    assert _compact(html) == _compact(expected)


def test_deep_nested_two_levels() -> None:
    # Parent ':' → numeric ':' → roman grandchildren — typical FEK hierarchy.
    lines = ["- Θεματικές:", "1) Ορισμοί:", "i) Όρος Α", "ii) Όρος Β"]
    html = lines_to_html(lines)
    expected = (
        "<ul>"
        "<li>Θεματικές:"
        "<ul>"
        "<li>Ορισμοί:"
        "<ul><li>Όρος Α</li><li>Όρος Β</li></ul>"
        "</li>"
        "</ul>"
        "</li>"
        "</ul>"
    )
    assert _compact(html) == _compact(expected)


def test_mixed_kinds_and_pop_levels() -> None:
    # After roman grandchildren, a dash returns to the outer list.
    lines = [
        "- Ρυθμίσεις:",
        "1) Μηχανισμοί:",
        "i) Υποενότητα",
        "- Επιστροφή στο ανώτερο επίπεδο",
    ]
    html = lines_to_html(lines)
    expected = (
        "<ul>"
        "<li>Ρυθμίσεις:"
        "<ul>"
        "<li>Μηχανισμοί:"
        "<ul><li>Υποενότητα</li></ul>"
        "</li>"
        "</ul>"
        "</li>"
        "<li>Επιστροφή στο ανώτερο επίπεδο</li>"
        "</ul>"
    )
    assert _compact(html) == _compact(expected)


# -------------------------
# Blank lines inside lists (UL coalescing)
# -------------------------


def test_blank_lines_inside_list_do_not_split_ul() -> None:
    lines = ["- Α", "", " ", "- Β", " ", "", "- Γ"]
    html = lines_to_html(lines)
    expected = "<ul><li>Α</li><li>Β</li><li>Γ</li></ul>"
    assert _compact(html) == _compact(expected)


def test_coalesce_adjacent_uls_created_by_blank_chunks() -> None:
    lines = ["- Α", "- Β", "", "- Γ"]
    html = lines_to_html(lines)
    # Implementation coalesces </ul><ul> into a single UL block.
    expected = "<ul><li>Α</li><li>Β</li><li>Γ</li></ul>"
    assert _compact(html) == _compact(expected)
