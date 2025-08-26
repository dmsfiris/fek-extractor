from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional


@dataclass(slots=True)
class ExtractRecord:
    """Structured info returned for each PDF."""
    path: str
    filename: str
    pages: int
    length: int
    num_lines: int
    median_line_length: float
    char_counts: Dict[str, int] = field(default_factory=dict)
    word_counts_top: Dict[str, int] = field(default_factory=dict)
    matches: Dict[str, List[str]] = field(default_factory=dict)
    first_5_lines: List[str] = field(default_factory=list)
    error: Optional[str] = None
