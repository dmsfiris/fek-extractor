from pathlib import Path

from fek_extractor.cli import collect_pdfs


def test_collect_pdfs(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n")  # stub
    (tmp_path / "b.txt").write_text("nope")
    files = collect_pdfs(tmp_path, recursive=False)
    assert [p.name for p in files] == ["a.pdf"]
