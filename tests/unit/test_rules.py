from fek_extractor.parsing.rules import parse_text

def test_parse_text_counts():
    text = "Alpha beta beta GAMMA. Alpha!"
    parsed = parse_text(text, patterns=[r"alpha", r"beta"])
    assert parsed["word_counts_top"].get("alpha") == 2
    assert len(parsed["matches"][r"alpha"]) == 2
    assert len(parsed["matches"][r"beta"]) == 2
