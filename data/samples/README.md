# Sample FEK PDFs (`data/samples/`)

Small, legally-redistributable **Greek Government Gazette (ΦΕΚ)** PDFs used for local testing and demos.

> These samples are curated to cover key FEK edge cases—premature column endings, annex pages, TOC presence, and signature placement—so you can validate column/tail handling, reading order, and article stitching in a controlled, reproducible way.

---

## Included files

- `gr-act-2020-4706-4706_2020.pdf` — example FEK act (2020), typical two-column layout; columns end prematurely on the last page (useful for testing tail/flow handling) and includes a Table of Contents (TOC).
- `gr-act-2018-4514-4514_2018.pdf` — example FEK act (2018), typical two-column layout; includes annexes (useful for testing appendix/tail handling).
- `3606_2007.pdf` — example FEK act (2007), legacy formatting quirks; signatures appear inside the double-column body, whereas in the other samples signatures sit below the columns (tail region).

If you add or rename files, please document their key quirks (e.g., TOC presence, annexes, signature placement, premature column endings) and update this list.

---

## How to use these samples

Run the extractor on individual files:

```bash
# JSON (default)
fek-extractor -i data/samples/gr-act-2020-4706-4706_2020.pdf -o out-4706-2020.json

# JSON (default) + debug focused on a specific page (replace N)
fek-extractor -i data/samples/gr-act-2020-4706-4706_2020.pdf -o out-4706-2020.json --debug N

# Articles map only (JSON)
fek-extractor -i data/samples/3606_2007.pdf --articles-only -o articles-3606-2007.json

# TOC only (JSON)
fek-extractor -i data/samples/gr-act-2020-4706-4706_2020.pdf --toc-only -o toc-4706-2020.json
```

Use the directory to process all samples:

```bash
fek-extractor -i data/samples -o out-samples.json
```

---

## Provenance & legal note

- In Greece, **official texts expressing the authority of the State** (e.g., **legislative, administrative, and judicial texts**) are generally **excluded from copyright** (Law 2121/1993, Article 2(5)).
- The PDFs in this folder are provided **solely for demonstration and testing**.

---

## Contact

Need tailored FEK pipelines or Greek‑aware NLP? **[AspectSoft](https://aspectsoft.gr)** can help.
