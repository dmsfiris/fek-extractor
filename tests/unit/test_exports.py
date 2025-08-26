from pathlib import Path

from fek_extractor.io.exports import write_csv, write_json


def test_write_json_and_csv(tmp_path: Path):
    records = [
        {
            "path": "x.pdf",
            "filename": "x.pdf",
            "pages": 1,
            "length": 10,
            "num_lines": 1,
            "median_line_length": 10,
            "matches": {},
            "char_counts": {},
            "word_counts_top": {},
            "first_5_lines": [],
        }
    ]
    write_json(records, tmp_path / "out.json")
    write_csv(records, tmp_path / "out.csv")
    assert (tmp_path / "out.json").exists()
    assert (tmp_path / "out.csv").exists()
