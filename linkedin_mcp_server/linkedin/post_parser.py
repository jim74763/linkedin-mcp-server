"""Turn the rendered text of a list of posts into structured posts.

Used wherever the server returns posts: a member's activity, a company's posts,
the home feed and post search. The text is in the interface language of the
account, so the parse leans on what does not change with it:

- each post opens with a ``Feed post number N`` style heading (the ``Feed``
  prefix and the closing number are what is matched, not the words between);
  where there are none, a run of action buttons ends a post instead;
- the author is the first line, the time is the first short ``<n><unit>`` line;
- the counters sit in the tail of the post, and are told apart by the noun after
  the number (``ui_labels``), the one place a table is unavoidable.

A permalink is attached only when the page gave exactly one per post, in page
order, because the permalinks come from a different part of the page than the
text and nothing in the text ties one to the other.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


from linkedin_mcp_server.core.exceptions import InvalidReferenceError
from linkedin_mcp_server.linkedin.identifiers import (
    normalize_post_reference,
    post_update_url,
)
from linkedin_mcp_server.linkedin.ui_labels import (
    count_label,
    is_action_label,
    is_degree_badge,
    POST_HEADING,
    is_relative_time,
    non_empty_lines,
    reaction_total,
    relative_time_text,
)

# Buttons that sit between a post's header and its text, and carry no text of
# the post. Per-locale because they have no shape of their own.
_HEADER_BUTTONS = frozenset(
    {
        "follow",
        "following",
        "+ follow",
        "volgen",
        "+ volgen",
        "volgend",
        "folgen",
        "+ folgen",
        "suivre",
        "+ suivre",
        "seguir",
        "+ seguir",
        "segui",
        "+ segui",
    }
)

# How many lines from the top of a post its relative time may sit.
_HEADER_WINDOW = 8

# How far back from the first counter or button the reaction total may sit.
_REACTION_WINDOW = 3

# Counts the parser keeps on a post.
_COUNT_FIELDS = ("reactions", "comments", "reposts", "impressions")


class PostItem(TypedDict):
    """One post, as returned to the caller."""

    index: int
    text: str
    reactions: int | None
    comments: int | None
    reposts: int | None
    impressions: int | None
    author: NotRequired[str]
    time: NotRequired[str]
    url: NotRequired[str]
    activity_id: NotRequired[str]


def _split_by_heading(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    for line in lines:
        if POST_HEADING.match(line):
            blocks.append([])
        elif blocks:
            blocks[-1].append(line)
    return blocks


def _split_by_action_rows(lines: list[str]) -> list[list[str]]:
    """Blocks that each end in a run of two or more action-button lines."""
    blocks: list[list[str]] = []
    current: list[str] = []
    run = 0
    for line in lines:
        if is_action_label(line):
            run += 1
            current.append(line)
            continue
        if run >= 2:
            blocks.append(current)
            current = []
        run = 0
        current.append(line)
    if run >= 2:
        blocks.append(current)
        current = []
    # Whatever follows the last button row is a post cut short; keep it only if
    # it looks like one.
    if any(is_relative_time(line) for line in current[:_HEADER_WINDOW]):
        blocks.append(current)
    return blocks


def _is_more_marker(line: str) -> bool:
    """The truncation tail ("...more", "…meer weergeven"): a short ellipsis line."""
    stripped = line.strip()
    return stripped.startswith(("…", "...")) and len(stripped.split()) <= 3


def _parse_block(lines: list[str], index: int) -> PostItem | None:
    if not lines:
        return None

    counts: dict[str, int | None] = dict.fromkeys(_COUNT_FIELDS)
    tail_start: int | None = None
    kept: list[tuple[int, str]] = []
    for position, line in enumerate(lines):
        labelled = count_label(line)
        if labelled is not None and labelled[0] in _COUNT_FIELDS:
            counts[labelled[0]] = labelled[1]
            if labelled[0] != "impressions" and tail_start is None and position > 0:
                tail_start = position
            continue
        if labelled is not None:
            # A reply counter belongs to a comment, not to the post.
            continue
        if is_action_label(line) and position > 0:
            if tail_start is None:
                tail_start = position
            continue
        kept.append((position, line))

    body_end = tail_start if tail_start is not None else len(lines)
    if tail_start is not None:
        for position in range(
            tail_start - 1, max(tail_start - 1 - _REACTION_WINDOW, -1), -1
        ):
            total = reaction_total(lines[position])
            if total is not None:
                counts["reactions"] = total
                body_end = position
                break

    head = [(p, line) for p, line in kept if p < body_end]
    time: str | None = None
    time_position: int | None = None
    for p, line in head[:_HEADER_WINDOW]:
        if is_relative_time(line):
            time, time_position = relative_time_text(line), p
            break

    author: str | None = None
    for _p, line in head:
        if not is_degree_badge(line):
            author = line
            break

    skip_until = time_position if time_position is not None else -1
    text_lines: list[str] = []
    for p, line in head:
        if p <= skip_until:
            continue
        if time_position is None and (line == author or is_degree_badge(line)):
            continue
        if line.casefold() in _HEADER_BUTTONS and not text_lines:
            continue
        if _is_more_marker(line):
            continue
        text_lines.append(line)

    item: PostItem = {
        "index": index,
        "text": "\n".join(text_lines).strip(),
        "reactions": counts["reactions"],
        "comments": counts["comments"],
        "reposts": counts["reposts"],
        "impressions": counts["impressions"],
    }
    if author:
        item["author"] = author
    if time:
        item["time"] = time
    if not item["text"] and not any(counts.values()) and not time:
        return None
    return item


def parse_posts(text: str) -> list[PostItem]:
    """The posts in a section's cleaned text, in page order, without permalinks."""
    lines = non_empty_lines(text)
    blocks = _split_by_heading(lines) or _split_by_action_rows(lines)
    posts: list[PostItem] = []
    for block in blocks:
        item = _parse_block(block, len(posts))
        if item is not None:
            posts.append(item)
    return posts


def permalinks(references: list[Any]) -> list[tuple[str, str]]:
    """``(permalink, id)`` per distinct post among the ``feed_post`` references.

    The two URL shapes LinkedIn uses for one post (``/feed/update/<urn>/`` and
    ``/posts/<slug>``) carry the same id, so they collapse to one entry.
    """
    seen: set[str] = set()
    found: list[tuple[str, str]] = []
    for reference in references:
        if not isinstance(reference, dict) or reference.get("kind") != "feed_post":
            continue
        try:
            kind, post_id = normalize_post_reference(str(reference.get("url", "")))
        except InvalidReferenceError:
            continue
        if post_id in seen:
            continue
        seen.add(post_id)
        found.append((post_update_url(kind, post_id), post_id))
    return found


def structured_posts(text: str, references: list[Any] | None = None) -> list[PostItem]:
    """Posts from *text*, each with its permalink when the page makes it certain."""
    posts = parse_posts(text)
    links = permalinks(references or [])
    if posts and len(links) == len(posts):
        for post, (url, post_id) in zip(posts, links, strict=True):
            post["url"] = url
            post["activity_id"] = post_id
    return posts


def with_posts(result: dict[str, Any], section: str) -> dict[str, Any]:
    """Add ``posts`` to a tool result built from *section*, when any were found.

    Left out entirely when the text held no recognisable post, so a result keeps
    exactly the shape it had before for pages the parser cannot read.
    """
    text = result.get("sections", {}).get(section)
    if not text:
        return result
    references = result.get("references", {}).get(section, [])
    posts = structured_posts(text, references)
    if posts:
        result["posts"] = posts
    return result
