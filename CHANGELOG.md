# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-09-10

### Added
- **First public release** with a stable CLI and Python API.
- **FEK-aware text extraction** with two-column segmentation (k-means + gutter valley), tail detection, and header/footer cleanup.
- **Region classification & demotion (`pdf.py`)**: classify header, footer, column body, full-width *tail*, noise; demote non-body blocks out of the main flow.
- **Greek de-hyphenation**: remove soft/discretionary hyphens; conservative word stitching with accent/case preservation.
- **Header parsing**: FEK series, issue number, dotted and ISO dates; best-effort decision numbers (“Αριθ.”).
- **Article detection**: recognize `Άρθρο N` (supports suffixes like `14Α`), capture titles/bodies, stitch across pages, build a normalized articles map.
- **TOC synthesis (optional)**: hierarchical structure (ΜΕΡΟΣ → ΤΙΤΛΟΣ → ΚΕΦΑΛΑΙΟ → ΤΜΗΜΑ → Άρθρα).
- **Metrics (optional)**: counts, top words, character histogram, pattern matches.
- **CLI options**: `--format {json,csv}`, `--articles-only`, `--toc-only`, `--jobs N`, `--no-recursive`, `--debug [PAGE]`.
- **Developer tooling**: type hints (PEP 561), `ruff`, `black`, `mypy`, `pytest`, `pre-commit` hooks.
- **Docs & meta**: README (features/usage/deep dive), LICENSE (Apache-2.0), NOTICE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, CITATION.cff.
- **Samples**: `data/samples/` README describing edge cases.

### Changed
- Polished CLI UX (clear help text, consistent option names).
- Stabilized public import surface (`from fek_extractor import extract_pdf_info`).

### Fixed
- Header detection on dotted/ISO date variants and spacing/diacritic quirks.
- De-hyphenation edge cases around hyphen+space line breaks.
- TOC node grouping when sections skip levels.

---

## [0.1.0-rc.1] - 2025-09-08

### Added
- Release-candidate hardening: logging polish, extra tests, error messages with actionable hints.
- Debug helper module: `python -m fek_extractor.debug --pdf <file> --page N --check-order`.
- Samples README with provenance/legal note and usage snippets.

### Changed
- Finalized output record keys and CLI option names for 0.1.0.
- Improved column gutter detection on narrow layouts.

### Fixed
- Windows path handling; UTF‑8 console issues in PowerShell.

---

## [0.1.0-beta.2] - 2025-09-04

### Added
- CSV writer and `--format csv` option.
- `--articles-only` and `--toc-only` JSON emitters.
- Pattern-matching registry (`data/patterns/patterns.txt`) for citations and “Θέμα:”.
- Basic metrics (lengths, counts, histograms).
- Parallel directory processing via `--jobs N`.

### Changed
- Column segmentation refined (gutter-valley fallback after k-means); tail threshold tuning.

### Fixed
- Page-order off-by-one in rare footer-heavy pages.

---

## [0.1.0-beta.1] - 2025-09-03

### Added
- Region classification & demotion in `pdf.py` (header/footer/column/tail/noise).
- Greek-aware normalization & de-hyphenation.
- Header parser (series/issue/date/decision number).
- Initial article detection and cross-page stitching.
- Basic CLI (`-i/--input`, `-o/--out`) and JSON writer.
- Unit test harness and initial fixtures.

### Changed
- Project layout to `src/`-style package; `pyproject.toml` packaging.

### Fixed
- Sorting stability in reading-order reconstruction.

---

## [0.0.5] - 2025-09-01

### Added
- Cross-page article stitching and title association.
- Early tail-region handling (below columns) to avoid mixing with body text.

### Fixed
- Duplicate line merging when glyph boxes overlap at column edges.

---

## [0.0.4] - 2025-08-27

### Added
- Two-column detection prototype (x-clustering) and initial gutter heuristics.
- Footer/header filtering hooks.
- Minimal debug logging.

---

## [0.0.3] - 2025-08-23

### Added
- CLI scaffold and JSON output writer.
- Initial directory traversal and basic logging.

---

## [0.0.2] - 2025-08-20

### Added
- Project skeleton with `src/fek_extractor/` layout.
- Type hints and tooling: `ruff`, `black`, `mypy`, `pytest`.
- GitHub Actions CI stub.

---

## [0.0.1] - 2025-08-19

### Added
- Initial proof of concept: PDF text extraction via `pdfminer.six` and naive line reconstruction.
