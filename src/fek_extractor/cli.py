from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any

from .core import extract_pdf_info
from .io.exports import write_csv, write_json
from .utils.logging import get_logger


def collect_pdfs(input_path: Path, recursive: bool = True) -> list[Path]:
    """Return a list of PDF paths from a file or directory."""
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    if input_path.is_dir():
        pattern = "**/*.pdf" if recursive else "*.pdf"
        return sorted(input_path.glob(pattern))
    raise FileNotFoundError(input_path)


def _load_patterns(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    """
    Merge --pattern (repeatable) with --patterns-file (one regex per line).
    Validate the patterns, de-duplicate, and return the final list.
    """
    user_patterns: list[str] = list(args.pattern or [])

    if args.patterns_file:
        if not args.patterns_file.exists():
            parser.error(f"--patterns-file not found: {args.patterns_file}")
        content = args.patterns_file.read_text(encoding="utf-8")
        file_rx = [
            ln.strip()
            for ln in content.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        user_patterns.extend(file_rx)

    # de-duplicate preserving order
    seen: set[str] = set()
    patterns: list[str] = []
    for pat in user_patterns:
        if pat not in seen:
            seen.add(pat)
            patterns.append(pat)

    # validate regexes early
    bad: list[tuple[str, str]] = []
    for pat in patterns:
        try:
            re.compile(pat, re.UNICODE | re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            bad.append((pat, str(e)))
    if bad:
        msg = "\n".join(f"  - {p!r}: {e}" for p, e in bad)
        parser.error(f"Invalid regex in --pattern/--patterns-file:\n{msg}")

    return patterns


def main() -> None:
    p = argparse.ArgumentParser(
        prog="fek-extractor",
        description="Extract structured info from FEK/Greek-law PDFs.",
    )
    p.add_argument("--input", "-i", type=Path, required=True, help="PDF file or directory")
    p.add_argument("--out", "-o", type=Path, default=Path("out.json"), help="Output path")
    p.add_argument("--format", "-f", choices=["json", "csv"], default="json", help="Output format")
    p.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="Regex to capture (repeatable). Use single quotes in PowerShell.",
    )
    p.add_argument(
        "--patterns-file",
        type=Path,
        default=None,
        help="Text file with one regex per line (lines starting with # are comments).",
    )
    p.add_argument("--no-recursive", action="store_true", help="Disable directory recursion")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set log verbosity (default: INFO).",
    )
    p.add_argument(
        "--dehyphenate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Join soft-wrapped hyphenated words in text (default: on).",
    )

    args = p.parse_args()

    # Configure logging
    get_logger().setLevel(getattr(logging, args.log_level.upper()))

    # Load/validate patterns
    patterns = _load_patterns(args, p)

    # Collect PDFs
    pdfs = collect_pdfs(args.input, recursive=not args.no_recursive)
    if not pdfs:
        raise SystemExit("No PDFs found.")

    # Process
    records: list[dict[str, Any]] = []
    for pdf in pdfs:
        try:
            records.append(extract_pdf_info(pdf, patterns=patterns, dehyphenate=args.dehyphenate))
        except Exception as e:  # continue on error, record it
            records.append({"path": str(pdf), "filename": pdf.name, "error": str(e)})

    # Output
    if args.format == "json":
        write_json(records, args.out)
        print(f"Wrote JSON to {args.out}")
    else:
        write_csv(records, args.out)
        print(f"Wrote CSV to {args.out}")


if __name__ == "__main__":
    main()
