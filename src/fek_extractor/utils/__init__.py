"""
fek_extractor.utils

Utility functions for FEK extraction/normalization.

Re-exports:
    - tidy_article_html(html: str) -> str
"""

from __future__ import annotations

# Re-export the HTML cleanup entrypoint
from .html_cleanup import tidy_article_html

__all__ = ["tidy_article_html"]
