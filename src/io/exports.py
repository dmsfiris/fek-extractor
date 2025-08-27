from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_json(records: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def write_csv(records: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        with out_path.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    base_keys = ["path", "filename", "pages", "length", "num_lines", "median_line_length"]
    dynamic = sorted(set().union(*[set(r.keys()) for r in records]) - set(base_keys))
    header = base_keys + dynamic
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow(r)
