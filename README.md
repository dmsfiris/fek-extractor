# fek-extractor
[![PyPI version](https://img.shields.io/pypi/v/fek-extractor.svg)](https://pypi.org/project/fek-extractor/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#-requirements)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-green.svg)](LICENSE)
[![CI](https://github.com/dmsfiris/fek-extractor/actions/workflows/tests.yml/badge.svg?branch=master)](https://github.com/dmsfiris/fek-extractor/actions/workflows/tests.yml)
[![code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Extract structured data from Greek Government Gazette (ΦΕΚ) PDFs.

It turns messy, two‑column government PDFs into machine‑readable **JSON/CSV** with FEK metadata and a clean map of **Άρθρα** (articles).
Built on `pdfminer.six`, with careful two‑column handling, header/footer filtering, Greek‑aware de‑hyphenation, and article detection.

---
## About this project

Greek Government Gazette (ΦΕΚ) documents look uniform at a glance, but their **typesetting and structure are anything but**. Even “clean” digital PDFs hide quirks that trip up generic parsers and off‑the‑shelf AI:

- **Multi‑column reading order** with full‑width “tails”, footers, and boilerplate that disrupt token flow.
- **Title vs. body separation** where headings, subtitles, and continuations interleave across pages.
- **Dense legal cross‑references and amendments**, with nested exceptions and renumbered clauses.
- **Inconsistent numbering and metadata**, plus occasional encoding artifacts and discretionary hyphens.

This project addresses those realities with a **layout‑aware, domain‑specific pipeline** that prioritizes *determinism* and *inspectability*:

- **Layout‑aware text reconstruction** — two‑column segmentation (k‑means + gutter valley), “tail” detection, header/footer filtering, and stable reading order.
- **Article‑structure recovery** — detects `Άρθρο N`, associates titles and bodies across page boundaries, and synthesizes a hierarchical TOC when possible.
- **Greek‑aware normalization** — de‑hyphenates safely (soft/discretionary hyphens, wrapped words) while preserving accents/case.
- **Domain heuristics + light NLP hooks** — FEK masthead parsing (series/issue/date), decision numbers, and simple patterns for subject/Θέμα; extension points for NER and reference extraction.
- **Transparent debugging** — page‑focused debug mode and optional metrics so you can see *why* a page parsed a certain way.

**Who it’s for:** legal‑tech teams, data engineers, and researchers who need **reproducible, explainable** FEK extraction that won’t crumble on edge cases.
**Outcome:** **structured, searchable, dependable** data for automation, analysis, and integration.

If your team needs tailored FEK pipelines or additional NLP components, **[AspectSoft](https://aspectsoft.gr)** can help.

---

## Features

- **FEK-aware text extraction**
  - Two-column segmentation via k-means over x-coordinates with a gutter-valley heuristic.
  - Per-page region classification & demotion — header, footer, column body, full-width tail, noise.
  - “Tail” detection for full-width content (signatures, appendices, tables) below the columns.
  - Header/footer cleanup tuned to FEK mastheads and page furniture.
  - Deterministic reading order (by column → y → x); graceful single-column fallback.

- **Greek de-hyphenation**
  - Removes soft/discretionary hyphens (U+00AD) and stitches wrapped words safely.
  - Preserves accents/case; conservative rules to avoid over-merging.
  - Handles common typography patterns (e.g., hyphen + space breaks).

- **Header parsing**
  - Extracts FEK **series** (Α/Β/… including word→letter normalization), **issue number**, and **date** in both `DD.MM.YYYY` and ISO `YYYY-MM-DD`.
  - Best-effort detection of **decision numbers** (e.g., “Αριθ.”).
  - Tolerant to spacing/diacritic/punctuation variants.

- **Article detection**
  - Recognizes `Άρθρο N` (including letter suffixes like `14Α`) and captures **title + body**.
  - Stitches articles across page boundaries; keeps original and normalized numbering.
  - Produces a structured **articles map** for direct programmatic use.

- **TOC synthesis** *(optional)*
  - Builds a hierarchical TOC where present:
    **ΜΕΡΟΣ → ΤΙΤΛΟΣ → ΚΕΦΑΛΑΙΟ → ΤΜΗΜΑ → Άρθρα**.
  - Emits clean JSON for navigation, QA, or UI rendering.

- **Metrics** *(opt-in via `--include-metrics`)*
  - Lengths & counts (characters, words, lines) and median line length.
  - Top words, character histogram, and pluggable regex matches (e.g., FEK citations, “Θέμα:”).

- **CLI & Python API**
  - CLI: single file or directory recursion, JSON/CSV output, `--jobs N` for parallel processing, focused logging via `--debug [PAGE]`.
  - API: `extract_pdf_info(path, include_metrics=True|False, ...)` returns a ready-to-use record.

- **Typed codebase & tests**
  - Static typing (PEP 561), lint/format (ruff, black), type checks (mypy), and tests (pytest).
  - Clear module boundaries (`io/`, `parsing/`, `metrics/`, `cli.py`, `core.py`).

With this mix, FEK PDFs become consistent, navigable JSON/CSV with reliable metadata and article structure—ready for indexing, analytics, and automation.


> ✨ Sample PDF for testing ships in `data/samples/gr-act-2020-4706-4706_2020.pdf`.

---

## Table of contents

- [Demo \& screenshots](#demo--screenshots)
- [Requirements](#requirements)
- [Install](#install)
- [Quickstart](#quickstart)
- [CLI usage](#cli-usage)
- [Python API](#python-api)
- [Output schema](#output-schema)
- [Technical deep dive](#technical-deep-dive)
- [Architecture](#architecture)
- [Examples](#examples)
- [Debug helpers](#debug-helpers)
- [Performance tips](#performance-tips)
- [Project layout](#project-layout)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## Demo & screenshots

![FEK extractor — debug view (4514/2018, page 12)](docs/assets/4514-debug-page-12.jpg)

---

## Requirements

- **Python 3.10+**
- **OS:** Linux, macOS, or Windows
- **Runtime dependency:** [`pdfminer.six`](https://github.com/pdfminer/pdfminer.six)

---

## Install

### From PyPI

```bash
pip install fek-extractor
```

### From source (editable)

```bash
git clone https://github.com/dmsfiris/fek-extractor.git
cd fek-extractor
python -m venv .venv
source .venv/bin/activate # Windows: .\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e . # library + CLI
# or full dev setup
pip install -e ".[dev]"
pre-commit install
```

### With pipx (isolated CLI)

```bash
pipx install fek-extractor
```

### Docker (no local Python needed)

```bash
docker run --rm -v "$PWD:/work" -w /work python:3.11-slim bash -lc "pip install fek-extractor && fek-extractor -i data/samples -o out.json"
```

---

## Quickstart

```bash
# JSON (default)
fek-extractor -i data/samples -o out.json -f json

# CSV
fek-extractor -i data/samples -o out.csv -f csv

# As a module (equivalent to the CLI)
python -m fek_extractor -i data/samples -o out.json
```

---

## CLI usage

```
usage: fek-extractor [-h] --input INPUT [--out OUT] [--format {json,csv}]
 [--no-recursive] [--debug [PAGE]] [--jobs JOBS]
 [--include-metrics] [--articles-only] [--toc-only]

Extract structured info from FEK/Greek-law PDFs.
```

**Options**

- `-i, --input PATH` (required) — PDF *file* or *directory*.
- `-o, --out PATH` (default: `out.json`) — Output path.
- `-f, --format {json,csv}` (default: `json`) — Output format.
- `--no-recursive` — When `--input` is a directory, do **not** recurse.
- `--debug [PAGE]` — Enable debug logging; optionally pass a **page number**
 (e.g. `--debug 39`) to focus per‑page debug.
- `--jobs JOBS` — Parallel workers when input is a **folder** (default 1).
- `--include-metrics` — Add metrics into each record (see below).
- `--articles-only` — Emit **only** the articles map as JSON (ignores `-f csv`).
- `--toc-only` — Emit **only** the synthesized Table of Contents as JSON.

---

## Python API

```python
from fek_extractor import extract_pdf_info

# Single PDF → record (dict)
record = extract_pdf_info("data/samples/gr-act-2020-4706-4706_2020.pdf", include_metrics=True)
print(record["filename"], record["pages"], record["articles_count"])

# Optional kwargs (subject to change):
# debug=True
# debug_pages=[39] # focus page(s) for diagnostics
# dehyphenate=True # on by default
```

**Return type**: `dict[str, Any]` with the fields shown in [Output schema](#-output-schema).

---

## Output schema

Each **record** (per PDF) typically contains:

| Field | Type | Notes |
|------|------|------|
| `path` | string | Absolute or relative input path |
| `filename` | string | File name only |
| `pages` | int | Page count |
| `fek_series` | string? | Single Greek letter (e.g. `Α`) if detected |
| `fek_number` | string? | Issue number if detected |
| `fek_date` | string? | Dotted date `DD.MM.YYYY` |
| `fek_date_iso` | string? | ISO date `YYYY-MM-DD` |
| `decision_number` | string? | From “Αριθ.” if found |
| `subject` | string? | Document subject/Θέμα (best‑effort) |
| `articles` | object | Map of **article number → article object** |
| `articles_count` | int | Convenience total |
| `first_5_lines` | array | First few text lines (debugging aid) |
| **Metrics** *(only when `--include-metrics`)* |||
| `length` | int | Characters in raw text |
| `num_lines` | int | Number of lines |
| `median_line_length` | int | Median non‑empty line length |
| `char_counts` | object | Char → count |
| `word_counts_top` | object | Top words |
| `chars`, `words` | int | Totals |
| `matches` | object | Regex matches (from `data/patterns/patterns.txt`) |

**Article object**

```jsonc
{
 "number": "13", // normalized article id (e.g., "13", "14Α")
 "title": "Οργανωτικές ρυθμίσεις",
 "body": "…full text…",
 // optional structural context when present:
 "part_letter": "Α", "part_title": "…", // ΜΕΡΟΣ
 "title_letter": "I", "title_title": "…", // ΤΙΤΛΟΣ
 "chapter_letter": "1", "chapter_title": "…", // ΚΕΦΑΛΑΙΟ
 "section_letter": "Α", "section_title": "…" // ΤΜΗΜΑ
}
```

---

## Technical deep dive

- **Reading order reconstruction**
 Rebuilds logical lines from low‑level glyphs, sorts by column then by y/x to maintain human reading order.
- **Two‑column segmentation**
 Uses k‑means clustering over x‑coords and gap valley search to find the column gutter; detects and demotes “tail” (full‑width) content below columns.
- **Greek‑aware normalization**
 Removes soft hyphens, stitches wrapped words, preserves Greek capitalization/accents conservatively.
- **Header & masthead parsing**
 Regex/heuristics for FEK line (series/issue/date), dotted and ISO date, and decision numbers (`Αριθ.`).
- **Article detection & stitching**
 Recognizes `Άρθρο N` headings, associates titles/bodies across page boundaries, and builds a robust map.
- **TOC synthesis**
 Extracts hierarchical headers (ΜΕΡΟΣ/ΤΙΤΛΟΣ/ΚΕΦΑΛΑΙΟ/ΤΜΗΜΑ) when present.
- **Metrics**
 Character/word counts and frequency stats to help diagnose messy PDFs.

---

## Architecture

```
PDF → glyphs → lines → columns → normalized text
 → header parser → articles parser → {record}
 → (optional) metrics / TOC
 → JSON/CSV writer
```

Key modules (under `src/fek_extractor/`):

- `io/pdf.py` – low‑level extraction, column/tail logic
- `parsing/normalize.py` – de‑hyphenation & cleanup
- `parsing/headers.py` – FEK header parsing
- `parsing/articles.py` – article detection + body stitching
- `metrics.py` – optional stats
- `cli.py` – batch processing, JSON/CSV output

---

## Examples

```bash
# 1) All PDFs under a folder → JSON
fek-extractor -i ./data/samples -o out.json

# 2) Single PDF → CSV
fek-extractor -i ./data/samples/gr-act-2020-4706-4706_2020.pdf -o out.csv -f csv

# 3) Articles only (for a file)
fek-extractor -i ./data/samples/gr-act-2020-4706-4706_2020.pdf --articles-only -o articles.json

# 4) Table of Contents only (for a file)
fek-extractor -i ./data/samples/gr-act-2020-4706-4706_2020.pdf --toc-only -o toc.json

# 5) Process a directory in parallel with 4 workers, include metrics
fek-extractor -i ./data/samples --jobs 4 --include-metrics -o out.json
```

---

## Debug helpers

There is a small debug entrypoint to inspect **column extraction** and **page layout**:

```bash
python -m fek_extractor.debug --pdf data/samples/gr-act-2020-4706-4706_2020.pdf --page 39 --check-order
```

---

## Performance tips

- Prefer running with `--jobs N` on directories to parallelize across files.
- For very large gazettes, keep output as JSON first (CSV is slower with many nested keys).
- Pre‑process PDFs (deskew/OCR) if the source is scanned images.

---

## Project layout

```
src/fek_extractor/
 __main__.py # supports `python -m fek_extractor`
 cli.py # CLI entrypoint
 core.py # Orchestration
 io/ # PDF I/O and exporters
 parsing/ # Normalization & parsing rules (articles, headers, dates, HTML)
 metrics.py # Basic text metrics
 models.py # Typed record/contexts
 utils/ # Logging, HTML cleanup helpers

data/
 patterns/patterns.txt # Regexes for extra matches
 samples/ # Sample FEK PDF (optional)

tests/ # Unit/CLI/integration tests
docs/ # MkDocs starter (optional)
```

---

## Development

```bash
# clone and set up
git clone https://github.com/dmsfiris/fek-extractor.git
cd fek-extractor
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
pre-commit install

# run checks
ruff check .
black --check .
mypy src
pytest -q
```

---

## Contributing

Contributions are welcome! Please open an issue to discuss substantial changes first.
By contributing you agree to license your work under the project’s **Apache‑2.0** license.

---

## License

This project is licensed under **Apache License 2.0**. See [LICENSE](LICENSE).
If you prefer a copyleft model (keeping derivatives open), consider re‑licensing as **GPLv3/AGPLv3** or offering **dual‑licensing** (AGPL for community + commercial license via AspectSoft). See below for guidance.

### Picking a license (quick guide)

- **Max adoption, simple** → MIT or **Apache‑2.0** (Apache adds a patent grant and NOTICE).
- **Keep derivatives open** → **GPLv3** (apps), **AGPLv3** (network services).
- **File‑level copyleft with easier mixing** → **MPL‑2.0**.
- **Source‑available (not OSI)** → Business Source License (BUSL‑1.1), SSPL, Polyform (non‑commercial).

> For a project that still offers some protection, **Apache‑2.0** is a great default. If you want stronger reciprocity, choose **AGPLv3** or dual‑license.

**How to apply**

1. Add a `LICENSE` file (done).
2. Add a `NOTICE` file (done) and keep third‑party attributions.
3. Optionally add license headers to source files, e.g.:

```python
# Copyright (c) 2025 Your Name
# SPDX-License-Identifier: Apache-2.0
```

---

## Contact

- **Author:** Dimitrios S. Sfyris (AspectSoft)
- **Email:** info@aspectsoft.gr

- **LinkedIn:** https://www.linkedin.com/in/dimitrios-s-sfyris/

- **Get in touch:** If you need bespoke FEK parsing or similar layout‑aware NLP pipelines, reach out.

---

## Acknowledgements

- Built on top of [`pdfminer.six`](https://github.com/pdfminer/pdfminer.six).
- Includes heuristics tuned for FEK / Εφημερίδα της Κυβερνήσεως layouts.
