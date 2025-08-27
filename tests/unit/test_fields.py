from fek_extractor.parsing.rules import parse_text


def test_extract_fek_fields_and_subject_multiline():
    raw = (
        "ΦΕΚ Α 123/01.01.2024\n"
        "Αριθ. 4567\n"
        "ΘΕΜΑ: Δοκιμή θέματος με δεύτερη γραμμή\n"
        "συνέχεια θέματος εδώ.\n"
        "\n"
        "Κυρίως κείμενο..."
    )
    parsed = parse_text(raw)
    assert parsed["fek_series"].upper() == "Α"
    assert parsed["fek_number"] == "123"
    assert parsed["fek_date"] == "01.01.2024"
    assert parsed["fek_date_iso"] == "2024-01-01"
    assert parsed["decision_number"] == "4567"
    # Multiline subject collapsed into one line
    assert "δεύτερη" in parsed["subject"] and "γραμμή συνέχεια" not in parsed["subject"]
