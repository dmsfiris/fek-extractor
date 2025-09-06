# src/fek_extractor/__init__.py
from __future__ import annotations

from typing import Any

"""
Keep this init minimal to avoid heavy imports and circulars during test discovery.
Expose public API lazily via __getattr__.
"""

__all__ = ["extract_pdf_info", "__version__"]

try:  # pragma: no cover
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("fek-extractor")
except Exception:  # pragma: no cover
    __version__ = "0.0.0"


def __getattr__(name: str) -> Any:
    if name == "extract_pdf_info":
        from .core import extract_pdf_info

        return extract_pdf_info

    raise AttributeError(name)
