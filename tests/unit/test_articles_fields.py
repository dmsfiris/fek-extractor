# tests/test_articles_fields.py
import re
from typing import Any

from fek_extractor.parsing.articles import build_articles_map


def _extract(tokens: list[str]) -> dict[str, Any]:
    """Adapter: join token lines and feed the full text to the current API."""
    return build_articles_map("\n".join(tokens))


def _norm_letter(s: str | None) -> str:
    """Normalize Greek letter markers like 'Α΄' -> 'Α' (strip prime marks/whitespace)."""
    if not s:
        return ""
    return re.sub(r"[΄'′`´\s]+", "", s)


def _assert_article_fields(
    art: dict[str, Any],
    *,
    exp_num: str,
    exp_title_contains: str | None,
    exp_part_letter: str | None,
    exp_part_title: str | None,
    exp_title_letter: str | None,
    exp_title_title: str | None,
    exp_chapter_letter: str | None,
    exp_chapter_title: str | None,
) -> None:
    # Required keys present
    for k in (
        "title",
        "html",
        "part_letter",
        "part_title",
        "title_letter",
        "title_title",
        "chapter_letter",
        "chapter_title",
    ):
        assert k in art, f"missing key {k}"

    # Title basic shape
    assert isinstance(art["title"], str)
    assert art["title"].startswith(f"Άρθρο {exp_num}")
    if exp_title_contains:
        assert exp_title_contains in art["title"]

    # HTML present (string, maybe empty but should exist)
    assert isinstance(art["html"], str)

    # Context expectations (normalize letters to ignore prime marks)
    assert _norm_letter(art["part_letter"]) == (
        _norm_letter(exp_part_letter) if exp_part_letter else ""
    )
    if exp_part_title is None:
        assert art["part_title"] is None
    else:
        assert isinstance(art["part_title"], str) and exp_part_title in art["part_title"]

    assert _norm_letter(art["title_letter"]) == (
        _norm_letter(exp_title_letter) if exp_title_letter else ""
    )
    if exp_title_title is None:
        assert art["title_title"] is None
    else:
        assert isinstance(art["title_title"], str) and exp_title_title in art["title_title"]

    assert _norm_letter(art["chapter_letter"]) == (
        _norm_letter(exp_chapter_letter) if exp_chapter_letter else ""
    )
    if exp_chapter_title is None:
        assert art["chapter_title"] is None
    else:
        assert isinstance(art["chapter_title"], str) and exp_chapter_title in art["chapter_title"]


def test_fields_with_full_context_and_inline_title() -> None:
    tokens = [
        "ΜΕΡΟΣ Α΄ ΔΙΑΤΑΞΕΙΣ ΓΙΑ ΤΗΝ ΕΤΑΙΡΙΚΗ ΔΙΑΚΥΒΕΡΝΗΣΗ",
        "ΤΙΤΛΟΣ Α΄ ΓΕΝΙΚΑ",
        "ΚΕΦΑΛΑΙΟ Α΄ ΓΕΝΙΚΕΣ ΔΙΑΤΑΞΕΙΣ",
        "Άρθρο 1: Πεδίο εφαρμογής",
        "Κείμενο σώματος 1.",
    ]
    arts = _extract(tokens)
    a1 = arts["1"]

    _assert_article_fields(
        a1,
        exp_num="1",
        exp_title_contains="Πεδίο εφαρμογής",
        exp_part_letter="Α",
        exp_part_title="ΔΙΑΤΑΞΕΙΣ ΓΙΑ ΤΗΝ ΕΤΑΙΡΙΚΗ ΔΙΑΚΥΒΕΡΝΗΣΗ",
        exp_title_letter="Α",
        exp_title_title="ΓΕΝΙΚΑ",
        exp_chapter_letter="Α",
        exp_chapter_title="ΓΕΝΙΚΕΣ ΔΙΑΤΑΞΕΙΣ",
    )

    # HTML should include the body text
    assert "Κείμενο σώματος 1" in a1["html"]


def test_fields_when_title_is_on_next_line() -> None:
    tokens = [
        "ΜΕΡΟΣ Α΄ ΚΑΤΙ",
        "ΚΕΦΑΛΑΙΟ Α΄ ΚΑΤΙ ΑΛΛΟ",
        "Άρθρο 2",
        "Ορισμοί",
        "«Ρυθμιζόμενη αγορά»: …",
    ]
    arts = _extract(tokens)
    a2 = arts["2"]

    _assert_article_fields(
        a2,
        exp_num="2",
        exp_title_contains="Ορισμοί",
        exp_part_letter="Α",
        exp_part_title="ΚΑΤΙ",
        exp_title_letter=None,  # no ΤΙΤΛΟΣ in this scenario
        exp_title_title=None,
        exp_chapter_letter="Α",
        exp_chapter_title="ΚΑΤΙ ΑΛΛΟ",
    )
    assert "Ρυθμιζόμενη αγορά" in (a2["html"] or "")


def test_context_updates_between_articles() -> None:
    tokens = [
        "ΜΕΡΟΣ Α΄ ΠΛΑΙΣΙΟ",
        "ΚΕΦΑΛΑΙΟ Α΄ ΕΝΟΤΗΤΑ 1",
        "Άρθρο 1: Θέμα 1",
        "Σώμα 1",
        # Only chapter changes here:
        "ΚΕΦΑΛΑΙΟ Β΄ ΕΝΟΤΗΤΑ 2",
        "Άρθρο 2: Θέμα 2",
        "Σώμα 2",
        # Now both title and chapter change:
        "ΤΙΤΛΟΣ Β΄ ΕΙΔΙΚΟ",
        "ΚΕΦΑΛΑΙΟ Γ΄ ΕΝΟΤΗΤΑ 3",
        "Άρθρο 3",
        "Υποχρεώσεις",
        "Σώμα 3",
    ]
    arts = _extract(tokens)
    a1, a2, a3 = arts["1"], arts["2"], arts["3"]

    # a1 in A,A
    _assert_article_fields(
        a1,
        exp_num="1",
        exp_title_contains="Θέμα 1",
        exp_part_letter="Α",
        exp_part_title="ΠΛΑΙΣΙΟ",
        exp_title_letter=None,
        exp_title_title=None,
        exp_chapter_letter="Α",
        exp_chapter_title="ΕΝΟΤΗΤΑ 1",
    )

    # a2 still in Part A, Chapter B
    _assert_article_fields(
        a2,
        exp_num="2",
        exp_title_contains="Θέμα 2",
        exp_part_letter="Α",
        exp_part_title="ΠΛΑΙΣΙΟ",
        exp_title_letter=None,
        exp_title_title=None,
        exp_chapter_letter="Β",
        exp_chapter_title="ΕΝΟΤΗΤΑ 2",
    )

    # a3 in Part A, Title B, Chapter Γ; title comes from next line "Υποχρεώσεις"
    _assert_article_fields(
        a3,
        exp_num="3",
        exp_title_contains="Υποχρεώσεις",
        exp_part_letter="Α",
        exp_part_title="ΠΛΑΙΣΙΟ",
        exp_title_letter="Β",
        exp_title_title="ΕΙΔΙΚΟ",
        exp_chapter_letter="Γ",
        exp_chapter_title="ΕΝΟΤΗΤΑ 3",
    )


def test_defaults_when_no_context() -> None:
    tokens = [
        "Άρθρο 1: Αυτόνομο άρθρο",
        "Κείμενο χωρίς άλλο context.",
    ]
    arts = _extract(tokens)
    a1 = arts["1"]

    _assert_article_fields(
        a1,
        exp_num="1",
        exp_title_contains="Αυτόνομο άρθρο",
        exp_part_letter=None,
        exp_part_title=None,
        exp_title_letter=None,
        exp_title_title=None,
        exp_chapter_letter=None,
        exp_chapter_title=None,
    )
    assert "Κείμενο χωρίς" in a1["html"]


def test_html_renders_list_items() -> None:
    tokens = [
        "Άρθρο 5: Λίστα",
        "1. Πρώτο",
        "2. Δεύτερο",
        "α) Υπο-σημείο",
    ]
    arts = _extract(tokens)
    a5 = arts["5"]
    html = a5.get("html") or ""

    # Ensure items appear
    for t in ("Πρώτο", "Δεύτερο", "Υπο-σημείο"):
        assert t in html

    # Prefer list markup but don’t be brittle
    assert ("<ul" in html and "<li>" in html) or html.count("<p>") >= 3
