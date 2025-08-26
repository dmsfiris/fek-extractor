from fek_extractor.parsing.normalize import normalize_text


def test_normalize_text():
    s = " A\u00A0test\nwith\tmulti\tspace &amp; entities "
    assert normalize_text(s) == "A test with multi space & entities"
