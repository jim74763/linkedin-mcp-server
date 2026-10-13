"""Turn the cards on the notifications page into structured notifications.

A card's words are in the member's language, so nothing here reads them to
decide what happened. The kind of notification comes from where its links go: a
comment notification opens the post with the comment's URN in the query, a
reaction or mention opens the post, an invitation opens the network manager. The
words stay available as ``headline`` for the reader who can read them.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict
from urllib.parse import parse_qs, unquote, urlparse

import re

from linkedin_mcp_server.core.exceptions import InvalidReferenceError
from linkedin_mcp_server.linkedin.comment_parser import profile_slug
from linkedin_mcp_server.linkedin.identifiers import (
    normalize_post_reference,
    post_update_url,
)
from linkedin_mcp_server.linkedin.ui_labels import (
    count_label,
    is_action_label,
    is_degree_badge,
    is_relative_time,
    non_empty_lines,
    relative_time_text,
)

#: The notification lists a caller can ask for, and the page that holds each.
NOTIFICATION_FILTERS = ("all", "my_posts")


class Notification(TypedDict):
    """One notification, as returned to the caller."""

    index: int
    action_type: str
    headline: str
    actor: NotRequired[str]
    actor_url: NotRequired[str]
    snippet: NotRequired[str]
    time: NotRequired[str]
    post_url: NotRequired[str]
    url: NotRequired[str]


def _path(href: str) -> str:
    return urlparse(href).path if "://" in href else href.split("?", 1)[0]


def _query(href: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(href).query) if "?" in href else {}


def _post_of(href: str) -> str | None:
    """The canonical permalink of the post a link opens, or ``None``."""
    path = unquote(_path(href))
    if "/feed/update/" not in path and "/posts/" not in path:
        return None
    try:
        kind, post_id = normalize_post_reference(href)
    except InvalidReferenceError:
        return None
    return post_update_url(kind, post_id)


def classify_links(links: list[dict[str, Any]]) -> str:
    """The notification kind from where its links lead, locale independent."""
    hrefs = [str(link.get("href", "")) for link in links]
    for href in hrefs:
        query = _query(href)
        if any("comment" in key.lower() for key in query) or "commentUrn" in href:
            return "comment"
    for href in hrefs:
        if _post_of(href) is not None:
            return "post"
    ordered = (
        ("/jobs/", "job"),
        ("/mynetwork/", "invitation"),
        ("/invitation", "invitation"),
        ("/events/", "event"),
        ("/newsletters/", "article"),
        ("/pulse/", "article"),
        ("/company/", "company"),
        ("/in/", "profile"),
    )
    for marker, kind in ordered:
        if any(marker in _path(href) for href in hrefs):
            return kind
    return "other"


def _is_chrome(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if is_action_label(stripped) or is_degree_badge(stripped):
        return True
    if re.fullmatch(r"[•·|\W\d]+", stripped):
        return True
    return count_label(stripped) is not None


def parse_notifications(cards: list[dict[str, Any]]) -> list[Notification]:
    """Structured notifications from the page's cards, in page order."""
    notifications: list[Notification] = []
    for card in cards:
        lines = non_empty_lines(str(card.get("text", "")))
        links = [link for link in card.get("links", []) if isinstance(link, dict)]
        if not lines:
            continue

        time: str | None = None
        for line in reversed(lines):
            if is_relative_time(line):
                time = relative_time_text(line)
                lines = [other for other in lines if other != line]
                break

        actor = actor_url = None
        for link in links:
            slug = profile_slug(str(link.get("href", "")))
            name = str(link.get("text", "")).strip()
            if slug and name:
                actor, actor_url = name.split(" • ")[0].strip(), f"/in/{slug}/"
                break

        kept: list[str] = []
        for line in lines:
            if _is_chrome(line) or line in kept:
                continue
            kept.append(line)
        if not kept:
            continue
        named = [line for line in kept if actor and actor.casefold() in line.casefold()]
        # The card repeats the actor's name on a line of its own for screen
        # readers; the sentence that goes on to say what happened is the headline.
        headline = next(
            (line for line in named if line.casefold() != (actor or "").casefold()),
            named[0] if named else kept[0],
        )
        rest = [
            line
            for line in kept
            if line != headline and line.casefold() != (actor or "").casefold()
        ]

        notification: Notification = {
            "index": len(notifications),
            "action_type": classify_links(links),
            "headline": headline,
        }
        if actor and actor_url:
            notification["actor"] = actor
            notification["actor_url"] = actor_url
        if rest:
            notification["snippet"] = "\n".join(rest)
        if time:
            notification["time"] = time
        for link in links:
            post_url = _post_of(str(link.get("href", "")))
            if post_url:
                notification["post_url"] = post_url
                break
        first = next((str(link.get("href", "")) for link in links), "")
        target = _path(first)
        if target.startswith("/"):
            notification["url"] = target
        notifications.append(notification)
    return notifications
