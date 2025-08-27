from __future__ import annotations

from fek_extractor.parsing.titles import (
    extract_article_number,
    is_article_head_line,
    split_inline_title_and_body,
)


def test_is_article_head_line_basic():
    assert is_article_head_line("Άρθρο 1")
    assert is_article_head_line("  Άρθρο 12   ")
    assert is_article_head_line("ΑΡΘΡΟ 3")
    assert not is_article_head_line("Κείμενο χωρίς άρθρο")


def test_extract_article_number():
    assert extract_article_number("Άρθρο 1") == 1
    assert extract_article_number("ΑΡΘΡΟ 12") == 12
    assert extract_article_number("Άρθρο 123 — Τίτλος") == 123
    assert extract_article_number("Χωρίς άρθρο") is None


def test_split_inline_title_and_body():
    title, body = split_inline_title_and_body("Άρθρο 3 — Τίτλος άρθρου")
    assert title == "Τίτλος άρθρου" and body == ""

    title2, body2 = split_inline_title_and_body("Άρθρο 2: Περιεχόμενο")
    assert title2 == "Περιεχόμενο" and body2 == ""

    title3, body3 = split_inline_title_and_body("Άρθρο 4")
    assert title3.startswith("Άρθρο 4") and body3 == ""
