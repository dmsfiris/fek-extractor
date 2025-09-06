# src/fek_extractor/cli.py
from __future__ import annotations

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
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


def _process_pdf(
    pdf: Path,
    include_metrics: bool,
    debug: bool,
) -> dict[str, Any]:
    """
    Worker that returns a plain dict for JSON/CSV.
    Keeps the signature simple for ProcessPoolExecutor pickling.
    """
    try:
        rec = extract_pdf_info(
            pdf,
            include_metrics=include_metrics,
            debug=debug,
        )
        return dict(rec)
    except Exception as e:
        return {"path": str(pdf), "filename": pdf.name, "error": str(e)}


def _articles_only_payload(records: list[dict[str, Any]]) -> Any:
    """
    Single PDF  -> return the articles map (dict of numeric keys).
    Multi PDFs  -> return { filename|path : articles_map }
    Falls back gracefully if structure isn't present.
    """

    def _pick_articles(rec: dict[str, Any]) -> Any:
        # 1) common shape: {"articles": {...}}
        arts = rec.get("articles")
        if isinstance(arts, dict):
            return arts
        # 2) sometimes the whole record is the articles map
        if rec and all(isinstance(k, str) and k.isdigit() for k in rec):
            return rec
        # 3) error passthrough
        if "error" in rec:
            return {"error": rec["error"]}
        return None

    if len(records) == 1:
        return _pick_articles(records[0])

    out: dict[str, Any] = {}
    for rec in records:
        key = rec.get("filename") or rec.get("path") or "document"
        out[key] = _pick_articles(rec)
    return out


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
        help="Regex to capture (repeatable). (Currently informational.)",
    )
    p.add_argument("--no-recursive", action="store_true", help="Disable directory recursion")
    p.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Verbose PDF splitter/debug logs (use --debug / --no-debug).",
    )
    p.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=1,
        help="Parallel workers for folder input (default: 1 = sequential).",
    )
    p.add_argument(
        "--include-metrics",
        action="store_true",
        help=(
            "Include metrics (length/lines/char_counts/word_counts_top/matches) "
            "in the output. By default they are omitted."
        ),
    )
    p.add_argument(
        "--articles-only",
        "--articles_only",
        dest="articles_only",
        action="store_true",
        help="Print only the articles map (numeric keys) as JSON.",
    )

    args = p.parse_args()

    # Configure logging level based on --debug
    get_logger().setLevel(logging.DEBUG if args.debug else logging.INFO)

    # Collect PDFs
    pdfs = collect_pdfs(args.input, recursive=not args.no_recursive)
    if not pdfs:
        raise SystemExit("No PDFs found.")

    # Process
    records: list[dict[str, Any]] = []

    if len(pdfs) == 1 or args.jobs <= 1:
        # Sequential path
        for pdf in pdfs:
            records.append(_process_pdf(pdf, args.include_metrics, args.debug))
    else:
        # Parallel over files; preserve input order in results
        total = len(pdfs)
        index_by_pdf = {pdf: i for i, pdf in enumerate(pdfs)}
        results_ordered: list[dict[str, Any] | None] = [None] * total

        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futures = {
                ex.submit(_process_pdf, pdf, args.include_metrics, args.debug): pdf for pdf in pdfs
            }
            for done, fut in enumerate(as_completed(futures), start=1):
                pdf = futures[fut]
                i = index_by_pdf[pdf]
                results_ordered[i] = fut.result()
                print(f"[{done}/{total}] {pdf.name}")

        # Drop Nones, keep order
        records = [r for r in results_ordered if r is not None]

    # Optionally strip metrics unless requested
    if not args.include_metrics:
        metric_keys = {
            "chars",
            "words",
            "length",
            "num_lines",
            "median_line_length",
            "char_counts",
            "word_counts_top",
            "pattern_matches",
            "matches",
        }
        for r in records:
            for k in metric_keys:
                r.pop(k, None)

    # Output
    if args.articles_only:
        payload = _articles_only_payload(records)
        if args.format == "csv":
            print("Warning: --articles-only ignores --format=csv; writing JSON.", flush=True)
        write_json(payload, args.out)
        print(f"Wrote articles-only JSON to {args.out}")
        return

    if args.format == "json":
        write_json(records, args.out)
        print(f"Wrote JSON to {args.out}")
    else:
        write_csv(records, args.out)
        print(f"Wrote CSV to {args.out}")


if __name__ == "__main__":
    main()
