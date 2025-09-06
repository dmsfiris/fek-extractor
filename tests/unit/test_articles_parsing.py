# tests/unit/test_articles_parsing.py
from __future__ import annotations

import pytest
from fek_extractor.parsing.articles import (
    build_articles,
    build_articles_map,
    find_articles_in_text,
)
from fek_extractor.parsing.rules.shared import (
    balance_subtitle_with_body,
    stitch_article_range_stub_upstream,
)


def test_balance_subtitle_with_body_closes_parenthesis() -> None:
    # Subtitle is missing a closing ')'; first <p> closes it.
    subtitle = "Ορισμοί (άρθρο 1 στοιχείο 2 της Οδηγίας (ΕΕ) 2017/828"
    html = "<p>Για τους σκοπούς των άρθρων 25 ως 36)</p><p>Άλλο κείμενο.</p>"

    new_sub, new_html = balance_subtitle_with_body(subtitle, html, max_blocks=3)

    assert new_sub is not None
    assert new_sub.endswith(")")
    # The first <p> should have been consumed.
    assert "<p>Άλλο κείμενο.</p>" in new_html
    assert "Για τους σκοπούς" not in new_html


def test_stitch_article_range_stub_upstream() -> None:
    # First paragraphs: "Τα άρθρα" + "27 έως 31" (+ small 3rd p).
    html = (
        "<p>Τα άρθρα</p>" "<p>27 έως 31</p>" "<p>του παρόντος</p>" "<p>Το παρόν εφαρμόζεται...</p>"
    )
    stitched = stitch_article_range_stub_upstream(html)

    # Expect first p to be stitched together, and rest preserved.
    assert "<p>Τα άρθρα 27 έως 31 του παρόντος</p>" in stitched
    assert "<p>Το παρόν εφαρμόζεται..." in stitched


def test_find_articles_in_text_basic() -> None:
    # Raw text with a single capitalized "Άρθρο" heading line.
    text = (
        "Άρθρο 26: Ορισμοί (άρθρο 1 στοιχείο 2 της Οδηγίας (ΕΕ) 2017/828)\n"
        "Για τους σκοπούς των άρθρων 25 ως 36 ισχύουν οι ακόλουθοι ορισμοί:\n"
    )
    idx = find_articles_in_text(text)
    assert len(idx) == 1
    head_i, num, inline = idx[0]
    assert head_i == 0
    assert num == 26
    # Title should be the inline part after the number.
    assert inline is not None and inline.startswith("Ορισμοί (")


def test_build_articles_slices_body() -> None:
    # Two simple articles with inline titles; ensure slicing is correct.
    text = "Άρθρο 1: Σκοπός\n" "Το παρόν καθορίζει...\n" "Άρθρο 2: Πεδίο\n" "Εφαρμόζεται σε...\n"
    arts = build_articles(text)
    assert len(arts) == 2

    a1, a2 = arts[0], arts[1]
    assert a1["number"] == 1
    assert a1["title"] == "Σκοπός"
    assert "Το παρόν καθορίζει" in a1["body"]

    assert a2["number"] == 2
    assert a2["title"] == "Πεδίο"
    assert "Εφαρμόζεται σε" in a2["body"]


def test_build_articles_map_stitches_stub_and_keeps_inline_title() -> None:
    # Mimic the structure around a range stub at start of body.
    tokens = [
        "Άρθρο 31: Διαμεσολαβητές τρίτης χώρας (άρθρο 3ε της Οδηγίας (ΕΕ) 2017/828)",
        "Τα άρθρα",
        "27 έως 31",
        "του παρόντος εφαρμόζονται χωρίς διακρίσεις.",
        "Σχετικές ρυθμίσεις ισχύουν αναλόγως.",
    ]
    out = build_articles_map("\n".join(tokens))
    assert "31" in out

    art31 = out["31"]
    assert art31["title"].startswith("Άρθρο 31: Διαμεσολαβητές τρίτης χώρας")

    # HTML should have the stitched first paragraph.
    html = art31["html"] or ""
    assert (
        "<p>Τα άρθρα 27 έως 31 του παρόντος εφαρμόζονται χωρίς διακρίσεις.</p>" in html
        or "Τα άρθρα 27 έως 31 του παρόντος εφαρμόζονται χωρίς διακρίσεις." in html
    )
    # The next sentence should still be present.
    assert "Σχετικές ρυθμίσεις ισχύουν αναλόγως." in html


def test_build_articles_map_fallback_subtitle_when_no_inline_title() -> None:
    # If the heading has no inline title, next non-bullet/non-header capitalized
    # line becomes the subtitle (per conservative single-line picker).
    tokens = [
        "Άρθρο 10",
        "Ορισμοί",
        "Το παρόν περιλαμβάνει...",
    ]
    out = build_articles_map("\n".join(tokens))
    a10 = out["10"]
    assert a10["title"] == "Άρθρο 10: Ορισμοί"
    assert "Το παρόν περιλαμβάνει" in (a10["html"] or "")


def test_build_articles_map_skips_bullet_as_subtitle() -> None:
    # If the first line after the heading is bulletish, it should NOT be used as subtitle.
    tokens = [
        "Άρθρο 12",
        "- Στοιχείο α",
        "Το παρόν ορίζει τη διαδικασία.",
    ]
    out = build_articles_map("\n".join(tokens))
    a12 = out["12"]
    # No subtitle promoted from the dash line.
    assert a12["title"] == "Άρθρο 12"
    assert "Το παρόν ορίζει" in (a12["html"] or "")


@pytest.mark.parametrize(
    "line,should_match",
    [
        ("Άρθρο 5: Τίτλος", True),
        ("άρθρο 5: (πεζά, πρέπει να αγνοηθεί)", False),
        ("ΚΕΦΑΛΑΙΟ Α Τίτλος", False),
    ],
)
def test_find_articles_in_text_capitalized_only(line: str, should_match: bool) -> None:
    idx = find_articles_in_text(line + "\nΣώμα...")
    assert (len(idx) == 1) is should_match


def test_stitching_does_not_trigger_on_unrelated_paragraphs() -> None:
    # Should not stitch if second <p> doesn't look like a range continuation.
    html = "<p>Το κείμενο</p><p>που μοιάζει με συνέχεια</p><p>πρέπει να ενώνεται.</p>"
    stitched = stitch_article_range_stub_upstream(html)
    # Unchanged.
    assert stitched == "<p>Το κείμενο που μοιάζει με συνέχεια πρέπει να ενώνεται.</p>"
