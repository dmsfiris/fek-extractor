from __future__ import annotations

import json
from pathlib import Path

import pytest
from fek_extractor.core import extract_pdf_info

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "data" / "samples" / "gr-act-2020-4706-4706_2020.pdf"
BASELINE_JSON = ROOT / "tests" / "fixtures" / "gr-act-2020-4706-4706_2020.json"

pytestmark = [
    pytest.mark.skipif(not PDF.exists(), reason="sample PDF not present"),
    pytest.mark.skipif(not BASELINE_JSON.exists(), reason="baseline JSON not present"),
]


def test_extract_against_baseline() -> None:
    expected_list = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    assert isinstance(expected_list, list) and expected_list
    expected = expected_list[0]

    actual = extract_pdf_info(PDF)

    assert actual["filename"] == expected["filename"] == PDF.name
    assert actual["pages"] >= 1

    # Compare key FEK fields when present in the baseline
    for key in [
        "fek_series",
        "fek_number",
        "fek_date",
        "fek_date_iso",
        "decision_number",
    ]:
        if expected.get(key):
            assert actual.get(key) == expected.get(key)

    # Subject: allow small whitespace differences, compare a prefix
    if expected.get("subject"):
        exp_subj = expected["subject"].strip()
        act_subj = (actual.get("subject") or "").strip()
        assert act_subj.startswith(exp_subj[:20])

    # Basic metrics should exist
    for key in [
        "length",
        "num_lines",
        "median_line_length",
        "char_counts",
        "word_counts_top",
    ]:
        assert key in actual
