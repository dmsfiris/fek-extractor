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
    debug_pages: int | None,
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
            debug_pages=debug_pages,
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


def _build_toc_from_articles(articles: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Hierarchy:
      Part -> Title -> Chapter -> Section -> Articles
    If a Chapter has no Sections, its articles are attached directly under the Chapter.
    Missing letters/titles are rendered as empty strings.
    """
    from collections import OrderedDict

    parts_map: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
    for k, rec in articles.items():
        try:
            num = int(k)
        except Exception:
            continue

        title_display = (rec.get("title") or "").strip()
        part_letter = (rec.get("part_letter") or "") or ""
        part_title = (rec.get("part_title") or "") or ""
        title_letter = (rec.get("title_letter") or "") or ""
        title_title = (rec.get("title_title") or "") or ""
        chapter_letter = (rec.get("chapter_letter") or "") or ""
        chapter_title = (rec.get("chapter_title") or "") or ""
        section_letter = (rec.get("section_letter") or "") or ""
        section_title = (rec.get("section_title") or "") or ""

        # PART
        part_key = (part_letter, part_title)
        part_node = parts_map.get(part_key)
        if part_node is None:
            part_node = {"part_letter": part_letter, "part_title": part_title, "titles": []}
            part_node["_titles_map"] = OrderedDict()
            parts_map[part_key] = part_node

        # TITLE
        titles_map = part_node["_titles_map"]
        title_key = (title_letter, title_title)
        title_node = titles_map.get(title_key)
        if title_node is None:
            title_node = {"title_letter": title_letter, "title_title": title_title, "chapters": []}
            title_node["_chapters_map"] = OrderedDict()
            titles_map[title_key] = title_node
            part_node["titles"].append(title_node)

        # CHAPTER
        chapters_map = title_node["_chapters_map"]
        chap_key = (chapter_letter, chapter_title)
        chap_node = chapters_map.get(chap_key)
        if chap_node is None:
            chap_node = {
                "chapter_letter": chapter_letter,
                "chapter_title": chapter_title,
                "sections": [],
                "articles": [],
            }
            chap_node["_sections_map"] = OrderedDict()
            chapters_map[chap_key] = chap_node
            title_node["chapters"].append(chap_node)

        # SECTION (optional)
        sections_map = chap_node["_sections_map"]
        sec_key = (section_letter, section_title)
        if section_letter or section_title:
            sec_node = sections_map.get(sec_key)
            if sec_node is None:
                sec_node = {
                    "section_letter": section_letter,
                    "section_title": section_title,
                    "articles": [],
                }
                sections_map[sec_key] = sec_node
                chap_node["sections"].append(sec_node)
            sec_node["articles"].append({"num": num, "title": title_display})
        else:
            chap_node["articles"].append({"num": num, "title": title_display})

    # strip helper maps
    out: list[dict[str, Any]] = []
    for _, pnode in parts_map.items():
        for tnode in pnode.get("titles", []):
            for chnode in tnode.get("chapters", []):
                chnode.pop("_sections_map", None)
            tnode.pop("_chapters_map", None)
        pnode.pop("_titles_map", None)
        out.append(pnode)
    return out


def main() -> None:
    p = argparse.ArgumentParser(
        prog="fek-extractor",
        description="Extract structured info from FEK/Greek-law PDFs.",
    )
    p.add_argument("--input", "-i", type=Path, required=True, help="PDF file or directory")
    p.add_argument("--out", "-o", type=Path, default=Path("out.json"), help="Output path")
    p.add_argument("--format", "-f", choices=["json", "csv"], default="json", help="Output format")
    p.add_argument("--no-recursive", action="store_true", help="Disable directory recursion")

    # --debug [PAGE]  -> σκέτο ανάβει debug, με αριθμό περνάει και το debug_pages
    p.add_argument(
        "--debug",
        nargs="?",
        metavar="PAGE",
        const=0,
        type=int,
        help="Enable debug; optionally pass a page number (e.g. --debug 39).",
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
    p.add_argument(
        "--toc-only",
        action="store_true",
        help="Emit only the Table of Contents as JSON (array of parts).",
    )

    args: argparse.Namespace = p.parse_args()

    # Translate --debug into (debug: bool, debug_pages: Optional[int])
    if args.debug is None:
        debug = False
        debug_pages: int | None = None
    elif args.debug == 0:
        debug = True
        debug_pages = None
    else:
        debug = True
        debug_pages = args.debug

    # Configure logging level based on --debug
    get_logger().setLevel(logging.DEBUG if debug else logging.INFO)

    # Collect PDFs
    pdfs = collect_pdfs(args.input, recursive=not args.no_recursive)
    if not pdfs:
        raise SystemExit("No PDFs found.")

    # Process
    records: list[dict[str, Any]] = []

    if len(pdfs) == 1 or args.jobs <= 1:
        # Sequential path
        for pdf in pdfs:
            records.append(_process_pdf(pdf, args.include_metrics, debug, debug_pages))
    else:
        # Parallel over files; preserve input order in results
        total = len(pdfs)
        index_by_pdf = {pdf: i for i, pdf in enumerate(pdfs)}
        results_ordered: list[dict[str, Any] | None] = [None] * total

        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futures = {
                ex.submit(_process_pdf, pdf, args.include_metrics, debug, debug_pages): pdf
                for pdf in pdfs
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

    input_is_dir = args.input.is_dir()

    if args.toc_only:
        if input_is_dir:
            payload = []
            for rec in records:
                toc = _build_toc_from_articles(rec.get("articles") or {})
                payload.append(
                    {"path": rec.get("path"), "filename": rec.get("filename"), "toc": toc}
                )
        else:
            toc = _build_toc_from_articles(records[0].get("articles") or {})
            payload = toc
        if args.format == "csv":
            print("Warning: --toc-only ignores --format=csv; writing JSON.", flush=True)
        write_json(payload, args.out)
        print(f"Wrote TOC JSON to {args.out}")
        return

    if args.format == "json":
        write_json(records, args.out)
        print(f"Wrote JSON to {args.out}")
    else:
        write_csv(records, args.out)
        print(f"Wrote CSV to {args.out}")


if __name__ == "__main__":
    main()
