from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pdfminer.high_level import extract_text, extract_pages
from pdfminer.layout import LAParams, LTTextContainer, LTTextLine

from ..parsing.normalize import normalize_text


def extract_text_whole(pdf_path: Path) -> str:
    """Return the full extracted text for the PDF (may include form feed \f between pages)."""
    return extract_text(str(pdf_path)) or ""


def iter_lines_from_pdf(pdf_path: Path, laparams: Optional[LAParams] = None) -> List[str]:
    """Extract lines from a PDF using pdfminer.six page layout parsing."""
    laparams = laparams or LAParams(
        all_texts=True,
        line_margin=0.2,
        char_margin=2.0,
        word_margin=0.1,
        boxes_flow=None,
    )
    lines: List[str] = []
    for page_layout in extract_pages(str(pdf_path), laparams=laparams):
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                for text_line in element:
                    if isinstance(text_line, LTTextLine):
                        t = normalize_text(text_line.get_text())
                        if t:
                            lines.append(t)
    return lines
