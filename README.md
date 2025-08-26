# fek-extractor

A clean, typed extractor for FEK PDFs, using `pdfminer.six`. This is a **src/** layout.

## Quickstart (Windows PowerShell)

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e ".[dev]"
pre-commit install

# checks
ruff check .; black --check .; mypy src; pytest -q

# run on a folder of PDFs
fek-extractor -i .\data\samples -o out.json -f json
# or module-mode
python -m fek_extractor -i .\data\samples -o out.csv -f csv
```

## Layout
- `fek_extractor/io/` — PDF reading & exports
- `fek_extractor/parsing/` — normalization & rules
- `fek_extractor/core.py` — orchestration
- `fek_extractor/cli.py` — CLI interface

