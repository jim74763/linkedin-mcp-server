"""Read the notifications page."""

from __future__ import annotations

from typing import Any

import logging

from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from linkedin_mcp_server.linkedin.content import PageContentReader
from linkedin_mcp_server.linkedin.contracts import (
    FilterValidationError,
    rate_limited_section_error,
)
from linkedin_mcp_server.linkedin.navigation import PageNavigator
from linkedin_mcp_server.linkedin.notification_parser import (
    NOTIFICATION_FILTERS,
    parse_notifications,
)
from linkedin_mcp_server.linkedin.session import PageSession
from linkedin_mcp_server.linkedin.text import (
    filter_linkedin_noise_lines,
    truncate_linkedin_noise,
)

logger = logging.getLogger(__name__)

NOTIFICATIONS_URL = "https://www.linkedin.com/notifications/"

# The query value that selects each list. The "my posts" tab is the one the
# caller asked for by name; `all` is the page's own default.
_FILTER_QUERY = {"all": "", "my_posts": "?filter=my_posts"}

# A notification list scrolls in batches of about ten cards.
_CARDS_PER_SCROLL = 10

# One card per `article`. The tag is the only structure read: the class names
# around it are LinkedIn's layout and change without notice. Link text and
# targets are collected so the kind and the actor can come from the links.
_CARDS_JS = """() => Array.from(document.querySelectorAll('main article'))
    .slice(0, 300)
    .map(card => ({
        text: card.innerText || '',
        links: Array.from(card.querySelectorAll('a[href]')).slice(0, 12).map(
            anchor => ({
                href: anchor.getAttribute('href') || '',
                text: (anchor.innerText || anchor.textContent || '')
                    .replace(/\\s+/g, ' ').trim(),
            })
        ),
    }))"""


class NotificationReader:
    """Own the one workflow whose subject is the member's notifications."""

    def __init__(
        self,
        session: PageSession,
        navigator: PageNavigator,
        content: PageContentReader,
    ):
        self._session = session
        self._navigator = navigator
        self._content = content

    async def get_notifications(
        self, filter_by: str = "all", limit: int = 30
    ) -> dict[str, Any]:
        """Read the notifications page, optionally only the "My posts" list.

        Args:
            filter_by: ``"all"`` or ``"my_posts"`` (activity on the member's
                own posts).
            limit: How many notifications to return at most. The page is
                scrolled far enough to load about that many.

        Returns:
            ``{url, filter, notifications}``; ``sections["notifications"]``
            holds the cleaned page text only when no card could be structured.
        """
        if filter_by not in NOTIFICATION_FILTERS:
            raise FilterValidationError(
                f"filter_by must be one of {', '.join(NOTIFICATION_FILTERS)}; "
                f"got {filter_by!r}"
            )
        limit = max(1, limit)
        url = NOTIFICATIONS_URL + _FILTER_QUERY[filter_by]

        await self._navigator._navigate_to_page(url)
        await self._session.check_rate_limit()
        try:
            await self._session.page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            logger.debug("No <main> element found on %s", url)
        await self._session.dismiss_modal()

        await self._session.scroll_body(
            pause_time=1.0, max_scrolls=max(1, -(-limit // _CARDS_PER_SCROLL))
        )

        raw_result = await self._content._extract_root_content(["main"])
        raw = raw_result["text"]
        result: dict[str, Any] = {"url": url, "filter": filter_by}
        truncated = truncate_linkedin_noise(raw) if raw else ""
        if raw and raw.strip() and not truncated:
            result["notifications"] = []
            result["section_errors"] = {"notifications": rate_limited_section_error()}
            return result

        cards = await self._session.run_on_linkedin(_CARDS_JS)
        notifications = parse_notifications(cards if isinstance(cards, list) else [])
        result["notifications"] = notifications[:limit]
        if not notifications:
            cleaned = filter_linkedin_noise_lines(truncated)
            if cleaned:
                result["sections"] = {"notifications": cleaned}
        return result
