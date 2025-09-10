# Contributing to fek-extractor

Thanks for your interest in contributing!

## Ground rules

- Be respectful and follow our [Code of Conduct](CODE_OF_CONDUCT.md).
- Discuss sizeable changes in an issue before opening a PR.
- Keep changes focused and small where possible.

## Getting started

1. Fork the repo and create your branch from `main`.
2. Set up your environment:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -U pip && pip install -e ".[dev]"
   pre-commit install
   ```

3. Run the checks:

   ```bash
   ruff check .
   black --check .
   mypy src
   pytest -q
   ```

## Pull request checklist

- [ ] New/changed behavior is covered by tests.
- [ ] `ruff`, `black`, `mypy`, and `pytest` all pass locally.
- [ ] Docs/README updated where relevant.
- [ ] For user-visible changes, add an entry to `CHANGELOG.md` under "Unreleased".

## Commit conventions

- Conventional Commits are encouraged (e.g., `feat:`, `fix:`, `docs:`).
- Keep commit messages imperative and descriptive.
