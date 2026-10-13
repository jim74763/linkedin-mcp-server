"""Turn the rendered text of a post's comment section into structured comments.

The page offers no per-comment container worth depending on, so the comments are
recovered from two things that do not change with the interface language: the
order of the author links on the page, and the shape of the lines around them
(a name, a degree badge, a relative time). Every comment opens with its author's
name on a line of its own, and the profile links appear in the same order, so
the links say where each comment starts and who wrote it.
"""

from __future__ import annotations

from typing import Any, TypedDict
from urllib.parse import urlparse

import re

from linkedin_mcp_server.linkedin.ui_labels import (
    count_label,
    is_action_label,
    is_degree_badge,
    is_relative_time,
    is_sort_label,
    non_empty_lines,
    parse_count,
    relative_time_text,
)

#: The orderings a caller can ask for. ``None`` leaves LinkedIn's own default.
COMMENT_SORTS = ("relevant", "recent")

# Author links further apart than this on the page are different indents; the
# slack absorbs sub-pixel layout without merging a reply into its parent.
_INDENT_TOLERANCE = 8.0

# How many lines after the author's name the time may sit. The header is the
# name, a degree badge, a headline, and the time, in that order.
_HEADER_WINDOW = 6

# How many places down the link list the next comment's author may sit: the
# mentions in a body are links too, and sit between two authors.
_AUTHOR_LOOKAHEAD = 10


class Author(TypedDict, total=False):
    """One profile link read off the comment section, in page order."""

    href: str
    text: str
    left: float


class Comment(TypedDict, total=False):
    """One comment, as returned to the caller."""

    index: int
    author: str
    author_url: str
    text: str
    time: str
    depth: int
    reply_to: int


def profile_slug(href: str) -> str | None:
    """The member slug in a ``/in/<slug>`` link, or ``None``."""
    path = urlparse(href).path if "://" in href else href.split("?", 1)[0]
    match = re.search(r"/in/([^/?#]+)", path)
    return match.group(1) if match else None


def _author_name(text: str) -> str:
    """The display name in a link's text, before any degree badge or headline."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    return re.split(r"\s+[•·]\s*", first, maxsplit=1)[0].strip()


def distinct_authors(authors: list[Author]) -> list[tuple[str, str, float | None]]:
    """``(slug, name, left)`` per link that names a member, adjacent repeats merged.

    Each comment carries an avatar link and a name link to the same member, so
    the same slug twice in a row is one author.
    """
    result: list[tuple[str, str, float | None]] = []
    for author in authors:
        href = author.get("href", "")
        slug = profile_slug(href)
        name = _author_name(author.get("text", ""))
        if slug is None or not name:
            continue
        left = author.get("left")
        if result and result[-1][0] == slug and result[-1][1] == name:
            continue
        result.append((slug, name, left))
    return result


def block_starts(
    lines: list[str], authors: list[tuple[str, str, float | None]]
) -> list[tuple[int, int]]:
    """``(line index, author index)`` for the line that opens each comment.

    The first comment may belong to any author: the links before the comments
    (the post's own header, people who reacted, the composer) are not named in
    the lines that follow. After that the next opener is one of the next few
    authors, so a mention that is also a link cannot swallow the list.
    """
    starts: list[tuple[int, int]] = []
    pointer = 0
    for index, line in enumerate(lines):
        reach = len(authors) if not starts else pointer + _AUTHOR_LOOKAHEAD + 1
        for member in range(pointer, min(reach, len(authors))):
            if line.casefold() != authors[member][1].casefold():
                continue
            # A name repeated on the next line is the accessible copy of the
            # same heading, not a second comment.
            if starts and starts[-1][0] == index - 1 and starts[-1][1] == member:
                break
            starts.append((index, member))
            pointer = member + 1
            break
    return starts


def _is_chrome(line: str) -> bool:
    """A line that belongs to the action row or the reply counters."""
    stripped = line.strip()
    if not stripped:
        return True
    if is_action_label(stripped) or is_sort_label(stripped):
        return True
    if re.fullmatch(r"[|•·\W]+", stripped):
        return True
    if parse_count(stripped) is not None and re.fullmatch(
        r"[\d.,\s]+[kKmM]?", stripped
    ):
        return True
    return count_label(stripped) is not None


def _body(lines: list[str], name: str) -> tuple[str | None, str]:
    """The time and the text of one comment's lines (after its author line)."""
    time_at: int | None = None
    for offset, line in enumerate(lines[:_HEADER_WINDOW]):
        if is_relative_time(line):
            time_at = offset
            break
    if time_at is not None:
        time = relative_time_text(lines[time_at])
        rest = lines[time_at + 1 :]
    else:
        time = None
        rest = list(lines)
        # No time line: skip the repeated name and degree badge that open it.
        while rest and (
            rest[0].casefold() == name.casefold() or is_degree_badge(rest[0])
        ):
            rest.pop(0)
    while rest and _is_chrome(rest[-1]):
        rest.pop()
    return time, "\n".join(rest).strip()


def parse_comments(text: str, authors: list[Author]) -> list[Comment]:
    """Structured comments from a post page's cleaned text and its author links.

    Everything before the sort control belongs to the post itself and is left
    out; when the page shows no sort control the post's own author block, the
    first on the page, is dropped instead. An author the text never names cannot
    open a comment, so a link the parse could not place costs nothing.
    """
    lines = non_empty_lines(text)
    members = distinct_authors(authors)
    if not lines or not members:
        return []

    sort_at = next((i for i, line in enumerate(lines) if is_sort_label(line)), None)
    start_line = sort_at + 1 if sort_at is not None else 0
    starts = [
        (line_index + start_line, member)
        for line_index, member in block_starts(lines[start_line:], members)
    ]
    if sort_at is None and starts:
        # The post's own header opens the page and is not a comment.
        starts = starts[1:]
    if not starts:
        return []

    lefts = [members[member][2] for _line, member in starts]
    depths = _depths(lefts)

    comments: list[Comment] = []
    ancestors: list[tuple[int, int]] = []
    for position, (line_index, member) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        slug, name, _left = members[member]
        time, body = _body(lines[line_index + 1 : end], name)
        comment: Comment = {
            "index": position,
            "author": name,
            "author_url": f"/in/{slug}/",
            "text": body,
        }
        if time:
            comment["time"] = time
        depth = depths[position]
        if depth is not None:
            comment["depth"] = depth
            while ancestors and ancestors[-1][1] >= depth:
                ancestors.pop()
            if ancestors:
                comment["reply_to"] = ancestors[-1][0]
            ancestors.append((position, depth))
        comments.append(comment)
    return comments


def _depths(lefts: list[Any]) -> list[int | None]:
    """Nesting level per comment, from how far each author link is indented.

    Replies sit further right than the comment they answer, on every locale and
    layout, so the rank of the indent is the depth. ``None`` for every comment
    when the page gave no positions, which says nothing about nesting.
    """
    if not lefts or any(not isinstance(value, (int, float)) for value in lefts):
        return [None] * len(lefts)
    levels: list[float] = []
    for value in sorted(lefts):
        if not levels or value - levels[-1] > _INDENT_TOLERANCE:
            levels.append(value)
    return [
        next(i for i, level in enumerate(levels) if value - level <= _INDENT_TOLERANCE)
        for value in lefts
    ]
