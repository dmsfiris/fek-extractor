"""
fek_extractor package.
"""

from .core import extract_pdf_info
from .parsing.normalize import normalize_text
from .parsing.rules import parse_text

__all__ = ["extract_pdf_info", "normalize_text", "parse_text"]
__version__ = "0.1.0"
