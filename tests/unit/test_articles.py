from __future__ import annotations

from fek_extractor.parsing.articles import find_articles_in_text

SAMPLE = """
Προοίμιο κειμένου
Άρθρο 1
Γενικές διατάξεις και λοιπά.

ΑΡΘΡΟ 2 — Δικαιώματα και υποχρεώσεις
Κείμενο άρθρου 2...

  Άρθρο 3: Τελικές ρυθμίσεις
Κείμενο άρθρου 3...
""".strip()


def test_find_articles_in_text_basic():
    arts = find_articles_in_text(SAMPLE)
    nums = [a["number"] for a in arts]
    titles = [a["title"] for a in arts]

    assert nums == [1, 2, 3]
    # Title for 1 is the heading itself (no inline title)
    assert titles[0].startswith("Άρθρο 1")
    # Inline titles captured for 2 and 3
    assert "Δικαιώματα" in titles[1]
    assert "Τελικές" in titles[2]
