from __future__ import annotations

from fek_extractor.parsing.headers import find_fek_header_line, parse_fek_header


def test_find_and_parse_header_single_line():
    lines = ["ΚΥΒΕΡΝΗΣΗ ΤΗΣ ΕΛΛΑΔΑΣ", "ΦΕΚ Α 123/01.01.2024", "Κάτω μέρος"]
    hdr_line = find_fek_header_line(lines)
    assert hdr_line == "ΦΕΚ Α 123/01.01.2024"
    fields = parse_fek_header(hdr_line)
    assert fields["fek_series"].upper() == "Α"
    assert fields["fek_number"] == "123"
    assert fields["fek_date"] == "01.01.2024"


def test_find_header_joined_lines():
    lines = ["ΚΥΒΕΡΝΗΣΗ ΤΗΣ ΕΛΛΑΔΑΣ", "ΦΕΚ Α 123/01.01.", "2024 και λοιπά"]
    hdr_line = find_fek_header_line(lines)
    assert hdr_line is not None
    fields = parse_fek_header(hdr_line)
    assert fields["fek_number"] == "123"
    assert fields["fek_date"].endswith("2024")
