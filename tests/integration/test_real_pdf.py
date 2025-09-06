import json
from pathlib import Path

import pytest
from fek_extractor.core import extract_pdf_info

PDF = Path("data/samples/gr-act-2020-4706-4706_2020.pdf")
BASELINE_JSON = Path("tests/fixtures/gr-act-2020-4706-4706_2020.json")

pytestmark = pytest.mark.skipif(not PDF.exists(), reason="sample PDF not present")


def test_extract_against_baseline() -> None:
    expected_list = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    assert isinstance(expected_list, list) and expected_list
    expected = expected_list[0]

    # Request metrics explicitly to satisfy the assertions below.
    actual = extract_pdf_info(PDF, include_metrics=True)

    assert actual["filename"] == expected["filename"] == PDF.name
    assert actual["pages"] >= 1

    # Compare key FEK fields when present in the baseline
    for key in ["fek_series", "fek_number", "fek_date", "fek_date_iso", "decision_number"]:
        if expected.get(key):
            assert actual.get(key) == expected.get(key)

    # Basic metrics should exist (since include_metrics=True)
    for key in ["length", "num_lines", "median_line_length", "char_counts", "word_counts_top"]:
        assert key in actual
