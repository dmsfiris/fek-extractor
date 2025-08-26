from __future__ import annotations

from collections.abc import Iterable


def take(iterable: Iterable, n: int):
    """Return first n items from an iterable as a list."""
    out = []
    for i, item in enumerate(iterable):
        if i >= n:
            break
        out.append(item)
    return out
