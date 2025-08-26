from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .core import extract_pdf_info
from .io.exports import write_csv, write_json


def collect_pdfs(input_path: Path, recursive: bool = True) -> list[Path]:
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    if input_path.is_dir():
        pattern = "**/*.pdf" if recursive else "*.pdf"
        return sorted(input_path.glob(pattern))
    raise FileNotFoundError(input_path)


def main() -> None:
    p = argparse.ArgumentParser(
        prog="fek-extractor", description="Extract structured info from FEK PDFs."
    )
    p.add_argument("--input", "-i", type=Path, required=True, help="PDF file or directory")
    p.add_argument("--out", "-o", type=Path, default=Path("out.json"), help="Output path")
    p.add_argument("--format", "-f", choices=["json", "csv"], default="json")
    p.add_argument("--pattern", action="append", default=None, help="Regex to capture (repeatable)")
    p.add_argument("--no-recursive", action="store_true", help="Disable directory recursion")

    args = p.parse_args()

    pdfs = collect_pdfs(args.input, recursive=not args.no_recursive)
    if not pdfs:
        raise SystemExit("No PDFs found.")

    records: list[dict[str, Any]] = []
    for pdf in pdfs:
        try:
            records.append(extract_pdf_info(pdf, patterns=args.pattern))
        except Exception as e:
            records.append({"path": str(pdf), "filename": pdf.name, "error": str(e)})

    if args.format == "json":
        write_json(records, args.out)
    else:
        write_csv(records, args.out)

    print(f"Wrote {args.format.upper()} to {args.out}")
