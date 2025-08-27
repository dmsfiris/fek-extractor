# src/fek_extractor/parsing/articles.py
from __future__ import annotations

from typing import TypedDict

from .normalize import normalize_text
from .titles import (
    extract_article_number,
    is_article_head_line,
    split_inline_title_and_body,
)


class ArticleIndex(TypedDict):
    number: int
    title: str
    line_index: int


class Article(TypedDict):
    number: int
    title: str
    body: str
    start_line: int
    end_line: int  # exclusive


class TocEntry(TypedDict):
    number: int
    title: str


def find_articles_in_text(text: str) -> list[ArticleIndex]:
    """
    Scan text and return a lightweight index of article headings:
    [{number, title, line_index}, ...]
    """
    # Preserve line boundaries: normalize each line, not the whole block
    lines = [normalize_text(ln) for ln in text.splitlines()]
    results: list[ArticleIndex] = []

    for i, line in enumerate(lines):
        if not is_article_head_line(line):
            continue
        num = extract_article_number(line)
        if num is None:
            continue
        title, _ = split_inline_title_and_body(line)
        results.append(ArticleIndex(number=num, title=title, line_index=i))

    return results


def build_articles(text: str) -> list[Article]:
    """
    Slice the document into articles using detected headings.
    Returns a list with number, title, body, and line span.
    """
    lines = [normalize_text(ln) for ln in text.splitlines()]
    # Reuse the indexer on the same normalized line set
    index = find_articles_in_text("\n".join(lines))
    if not index:
        return []

    articles: list[Article] = []
    for i, head in enumerate(index):
        start = head["line_index"] + 1  # body starts after the heading line
        end = index[i + 1]["line_index"] if i + 1 < len(index) else len(lines)
        # keep only non-empty lines in the body
        body_lines = [ln for ln in lines[start:end] if ln.strip()]
        articles.append(
            Article(
                number=head["number"],
                title=head["title"],
                body="\n".join(body_lines).strip(),
                start_line=start,
                end_line=end,
            )
        )
    return articles


def build_toc(articles: list[Article]) -> list[TocEntry]:
    """Minimal table of contents: number + title."""
    return [TocEntry(number=a["number"], title=a["title"]) for a in articles]
