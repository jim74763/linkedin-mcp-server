"""Read the comments on one post."""

from __future__ import annotations

from typing import Any, cast

import logging

from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from linkedin_mcp_server.linkedin.comment_parser import (
    COMMENT_SORTS,
    Author,
    parse_comments,
)
from linkedin_mcp_server.linkedin.content import PageContentReader
from linkedin_mcp_server.linkedin.contracts import (
    RATE_LIMITED_SECTION_TEXT,
    FilterValidationError,
    rate_limited_section_error,
)
from linkedin_mcp_server.linkedin.identifiers import (
    normalize_post_reference,
    post_update_url,
)
from linkedin_mcp_server.linkedin.navigation import PageNavigator
from linkedin_mcp_server.linkedin.session import PageSession
from linkedin_mcp_server.linkedin.text import (
    filter_linkedin_noise_lines,
    truncate_linkedin_noise,
)
from linkedin_mcp_server.linkedin.ui_labels import (
    LOAD_MORE_COMMENTS_LABELS,
    SORT_RECENT_LABELS,
    SORT_RELEVANT_LABELS,
    non_empty_lines,
)

logger = logging.getLogger(__name__)

# Where each member link sits horizontally. A reply is indented under its
# parent, so the left edge is the one nesting signal that survives every
# language and every class-name change. Only profile links are read.
_AUTHOR_LINKS_JS = """() => Array.from(
    document.querySelectorAll('main a[href*="/in/"]')
).slice(0, 800).map(anchor => ({
    href: anchor.getAttribute('href') || '',
    text: (anchor.innerText || anchor.textContent || '')
        .replace(/\\s+/g, ' ').trim(),
    left: Math.round(anchor.getBoundingClientRect().left),
}))"""

# Settling time after a click that reorders or extends the list.
_SETTLE_SECONDS = 1.5


class CommentReader:
    """Own the one workflow whose subject is the comments under a post."""

    def __init__(
        self,
        session: PageSession,
        navigator: PageNavigator,
        content: PageContentReader,
    ):
        self._session = session
        self._navigator = navigator
        self._content = content

    async def get_post_comments(
        self,
        post: str,
        sort_by: str | None = None,
        max_load_more: int = 3,
    ) -> dict[str, Any]:
        """Read the comments under a post, optionally most recent first.

        Args:
            post: A post URL, an activity URN, or the numeric activity id.
            sort_by: ``"recent"`` or ``"relevant"``; ``None`` keeps LinkedIn's
                default order. The sort control is found by its visible label,
                so ``sort["applied"]`` says whether it was, and an unapplied
                sort leaves the comments in LinkedIn's default order.
            max_load_more: How many times to ask LinkedIn for more comments.

        Returns:
            ``{url, post, sort, comments}`` where each comment holds ``author``,
            ``author_url``, ``text`` and, where the page showed them, ``time``,
            ``depth`` and ``reply_to``. ``sections["comments"]`` carries the
            cleaned text only when no comment could be recovered from it.
        """
        if sort_by is not None and sort_by not in COMMENT_SORTS:
            raise FilterValidationError(
                f"sort_by must be one of {', '.join(COMMENT_SORTS)}; got {sort_by!r}"
            )
        kind, post_id = normalize_post_reference(post)
        url = post_update_url(kind, post_id)

        await self._navigator._navigate_to_page(url)
        await self._session.check_rate_limit()
        try:
            await self._session.page.wait_for_selector("main")
        except PlaywrightTimeoutError:
            logger.debug("No <main> element found on %s", url)
        await self._session.dismiss_modal()

        applied = False
        if sort_by is not None:
            applied = await self._apply_sort(sort_by)
        await self._load_more(max(0, max_load_more))

        raw_result = await self._content._extract_root_content(["main"])
        raw = raw_result["text"]
        result: dict[str, Any] = {
            "url": url,
            "post": {"kind": kind, "id": post_id, "url": url},
        }
        if sort_by is not None:
            result["sort"] = {"requested": sort_by, "applied": applied}

        truncated = truncate_linkedin_noise(raw) if raw else ""
        if raw and raw.strip() and not truncated:
            result["comments"] = []
            result["section_errors"] = {"comments": rate_limited_section_error()}
            return result
        cleaned = filter_linkedin_noise_lines(truncated)
        authors = await self._author_links()
        comments = parse_comments(cleaned, authors)
        result["comments"] = comments
        if not comments and cleaned and cleaned != RATE_LIMITED_SECTION_TEXT:
            # The parse found nothing to structure, so the text is the answer.
            result["sections"] = {"comments": cleaned}
        return result

    async def _author_links(self) -> list[Author]:
        links = await self._session.run_on_linkedin(_AUTHOR_LINKS_JS)
        if not isinstance(links, list):
            return []
        return [cast(Author, link) for link in links if isinstance(link, dict)]

    async def _main_lines(self) -> list[str]:
        raw_result = await self._content._extract_root_content(["main"])
        return non_empty_lines(raw_result["text"])

    async def _apply_sort(self, sort_by: str) -> bool:
        """Switch the comment order through the visible sort control."""
        wanted, current = (
            (SORT_RECENT_LABELS, SORT_RELEVANT_LABELS)
            if sort_by == "recent"
            else (SORT_RELEVANT_LABELS, SORT_RECENT_LABELS)
        )
        lines = {line.casefold() for line in await self._main_lines()}
        trigger_is_current = any(label.casefold() in lines for label in current)
        if not trigger_is_current:
            # The control already shows the wanted order, or there is no
            # control (one comment, comments off). The first is a success.
            return any(label.casefold() in lines for label in wanted)
        opened = False
        for label in current:
            if await self._content.click_button_by_text(label):
                opened = True
                break
        if not opened:
            return False
        await self._session.delay(0.5)
        for label in wanted:
            if await self._content.click_button_by_text(label, scope="body"):
                await self._session.delay(_SETTLE_SECONDS)
                return True
        return False

    async def _load_more(self, attempts: int) -> None:
        """Ask for further comments until the control disappears or the budget ends."""
        for _ in range(attempts):
            await self._session.scroll_body(pause_time=0.5, max_scrolls=3)
            clicked = False
            for label in LOAD_MORE_COMMENTS_LABELS:
                if await self._content.click_button_by_text(label):
                    clicked = True
                    break
            if not clicked:
                return
            await self._session.delay(_SETTLE_SECONDS)
