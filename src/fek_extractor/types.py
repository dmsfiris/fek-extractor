from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExtractRecord:
    """Structured info returned for each PDF."""

    path: str
    filename: str
    pages: int
    length: int
    num_lines: int
    median_line_length: float
    char_counts: dict[str, int] = field(default_factory=dict)
    word_counts_top: dict[str, int] = field(default_factory=dict)
    matches: dict[str, list[str]] = field(default_factory=dict)
    first_5_lines: list[str] = field(default_factory=list)
    error: str | None = None
