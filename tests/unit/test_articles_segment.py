from fek_extractor.parsing.articles import build_articles, build_toc

SAMPLE = """
Προοίμιο
Άρθρο 1
Κείμενο α
γραμμή 2

ΑΡΘΡΟ 2 — Τίτλος δύο
Σώμα β

  Άρθρο 3: Τελικός
Τέλος.
""".strip()


def test_build_articles_and_toc():
    arts = build_articles(SAMPLE)
    assert [a["number"] for a in arts] == [1, 2, 3]
    assert arts[0]["title"].startswith("Άρθρο 1")
    assert "Κείμενο α" in arts[0]["body"]
    assert "γραμμή 2" in arts[0]["body"]
    assert "Σώμα β" in arts[1]["body"]
    assert "Τέλος." in arts[2]["body"]

    toc = build_toc(arts)
    assert toc == [
        {"number": 1, "title": arts[0]["title"]},
        {"number": 2, "title": arts[1]["title"]},
        {"number": 3, "title": arts[2]["title"]},
    ]
