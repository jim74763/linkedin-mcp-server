"""Turn the rendered text of a people search into structured results.

A result card reads, top to bottom: the member's name, a connection-degree
badge, a headline, a location, and then its buttons. None of those lines carries
an attribute worth depending on, so the cards are found the way the comments
are: the profile links on the page give the names and slugs in order, and the
shape of the lines after each name (a degree badge, then two plain lines) gives
the rest. Nothing here depends on the interface language except the button
labels that end a card, and a missed label costs a line, not a result.
"""

from __future__ import annotations

import re
from typing import TypedDict

from linkedin_mcp_server.linkedin.comment_parser import (
    Author,
    block_starts,
    distinct_authors,
)
from linkedin_mcp_server.linkedin.ui_labels import (
    is_card_action,
    is_degree_badge,
    non_empty_lines,
    parse_degree,
)

# Name and badge on one line: "Maria Jansen • 2nd".
_INLINE_DEGREE = re.compile(r"^(?P<head>.+?)\s+[•·]\s*(?P<tail>\S{1,6})$")

# How many lines after a name the degree badge may sit.
_BADGE_WINDOW = 3


class PersonResult(TypedDict, total=False):
    """One person from a search, as returned to the caller."""

    name: str
    profile_slug: str
    profile_url: str
    headline: str
    location: str
    connection_degree: int
    connection_degree_or_more: bool


def _split_inline_degree(lines: list[str]) -> list[str]:
    """Put a badge that shares its line with a name on a line of its own."""
    result: list[str] = []
    for line in lines:
        match = _INLINE_DEGREE.match(line)
        if match and parse_degree(match.group("tail")) is not None:
            result.append(match.group("head"))
            result.append(f"• {match.group('tail')}")
        else:
            result.append(line)
    return result


def parse_people(text: str, authors: list[Author]) -> list[PersonResult]:
    """Structured people from a search page's text and its profile links."""
    lines = _split_inline_degree(non_empty_lines(text))
    members = distinct_authors(authors)
    if not lines or not members:
        return []
    starts = block_starts(lines, members)
    people: list[PersonResult] = []
    seen: set[str] = set()
    for position, (line_index, member) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        slug, name, _left = members[member]
        if slug in seen:
            continue
        seen.add(slug)
        person: PersonResult = {
            "name": name,
            "profile_slug": slug,
            "profile_url": f"/in/{slug}/",
        }
        rest = lines[line_index + 1 : end]
        rest = [line for line in rest if line.casefold() != name.casefold()]
        degree_at = next(
            (i for i, line in enumerate(rest[:_BADGE_WINDOW]) if is_degree_badge(line)),
            None,
        )
        if degree_at is not None:
            parsed = parse_degree(rest[degree_at])
            if parsed is not None:
                person["connection_degree"] = parsed[0]
                if parsed[1]:
                    person["connection_degree_or_more"] = True
            rest = rest[degree_at + 1 :]
        facts: list[str] = []
        for line in rest:
            if is_card_action(line):
                break
            facts.append(line)
            if len(facts) == 2:
                break
        if facts:
            person["headline"] = facts[0]
        if len(facts) > 1:
            person["location"] = facts[1]
        people.append(person)
    return people
