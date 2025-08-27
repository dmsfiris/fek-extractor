# dev.ps1 — one-touch lint/format/type/test
param(
  [ValidateSet('all','ruff','black','mypy','pytest')]
  [string]$Only = 'all',
  [switch]$Fix = $true,        # Ruff --fix (default on)
  [switch]$NoTests = $false,   # skip pytest when running "all"
  [string]$Path = '.'          # path to check (for Ruff)
)

$ErrorActionPreference = 'Stop'

# Activate venv if present
if (-not $env:VIRTUAL_ENV -and (Test-Path .\.venv\Scripts\Activate.ps1)) {
  . .\.venv\Scripts\Activate.ps1
}

function Run-Ruff {
  Write-Host "`n=== Ruff ===" -ForegroundColor Cyan
  $args = @('check')
  if ($Fix) { $args += '--fix' }
  $args += @('--force-exclude', $Path)
  ruff @args
}

function Run-Black {
  Write-Host "`n=== Black ===" -ForegroundColor Cyan
  black .
}

function Run-Mypy {
  Write-Host "`n=== mypy ===" -ForegroundColor Cyan
  mypy src
}

function Run-Pytest {
  Write-Host "`n=== pytest ===" -ForegroundColor Cyan
  pytest -q
}

switch ($Only) {
  'ruff'   { Run-Ruff; break }
  'black'  { Run-Black; break }
  'mypy'   { Run-Mypy; break }
  'pytest' { Run-Pytest; break }
  default {
    Run-Ruff
    Run-Black
    Run-Mypy
    if (-not $NoTests) { Run-Pytest } else { Write-Host "`n(Skipping tests)" -ForegroundColor Yellow }
  }
}

Write-Host "`nAll dev checks completed." -ForegroundColor Green
