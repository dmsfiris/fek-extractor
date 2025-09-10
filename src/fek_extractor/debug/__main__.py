"""Run with:
    python -m fek_extractor.debug \
        --pdf "data/samples/gr-act-2020-4706-4706_2020.pdf" \
        --page 39 --check-order
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable

from pdfminer.high_level import extract_pages

from fek_extractor.io.pdf import ColumnExtractor, PageContext, _iter_lines


def extract_single_page_text(pdf_path: str, page_no: int, debug: bool = True) -> str:
    if page_no <= 0:
        raise ValueError("page_no must be 1-based (>= 1).")
    ce = ColumnExtractor(debug=debug)
    for idx, layout in enumerate(extract_pages(pdf_path), start=1):  # 1-based
        if idx != page_no:
            continue
        lines = list(_iter_lines(layout))
        # Ensure concrete types for mypy: getattr can be Any|None
        ctx = PageContext(
            page_index=idx,
            width=float(getattr(layout, "width", 0.0) or 0.0),
            height=float(getattr(layout, "height", 0.0) or 0.0),
            rotation=int(getattr(layout, "rotate", 0) or 0),
        )
        return ce.process_page(ctx, lines)
    raise ValueError(f"Page {page_no} not found in {pdf_path}")


def find_positions(text: str, needles: Iterable[str]) -> dict[str, int]:
    res: dict[str, int] = {}
    for n in needles:
        try:
            res[n] = text.index(n)
        except ValueError:
            res[n] = -1
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Probe column logic on a single PDF page")
    ap.add_argument("--pdf", required=True, help="Path to the PDF")
    ap.add_argument("--page", type=int, default=39, help="1-based page number (default: 39)")
    ap.add_argument("--out", default=None, help="Optional path to write extracted page text")
    ap.add_argument("--no-debug", action="store_true", help="Disable ColumnExtractor debug logs")
    ap.add_argument(
        "--check-order",
        action="store_true",
        help="Assert that 'Άρθρο 92' appears before 'Άρθρο 93'",
    )
    ap.add_argument(
        "--find",
        nargs="*",
        default=[],
        help="Extra substrings to search and report their positions",
    )
    args = ap.parse_args(argv)

    try:
        text = extract_single_page_text(args.pdf, args.page, debug=(not args.no_debug))
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    print("\n===== EXTRACTED PAGE TEXT =====\n")
    print(text)

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"\n[Saved] {args.out}")
        except Exception as e:
            print(f"[WARN] Failed to save to {args.out}: {e}", file=sys.stderr)

    if args.check_order:
        pos = find_positions(text, ["Άρθρο 92", "Άρθρο 93"])
        p92, p93 = pos.get("Άρθρο 92", -1), pos.get("Άρθρο 93", -1)
        print("\n===== ORDER CHECK =====")
        print(f"Άρθρο 92 @ {p92}")
        print(f"Άρθρο 93 @ {p93}")
        if p92 == -1 or p93 == -1:
            print("[FAIL] Could not find both articles.", file=sys.stderr)
            return 1
        if p92 < p93:
            print("[OK] Article 92 appears before Article 93.")
        else:
            print("[FAIL] Article 93 appears before Article 92.", file=sys.stderr)
            return 1

    if args.find:
        pos = find_positions(text, args.find)
        print("\n===== FIND RESULTS =====")
        for needle, idx in pos.items():
            print(f"{repr(needle)} @ {idx}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
