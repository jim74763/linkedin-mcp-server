"""Tests for the notifications reader."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from linkedin_mcp_server.linkedin.content import PageContentReader
from linkedin_mcp_server.linkedin.contracts import FilterValidationError
from linkedin_mcp_server.linkedin.navigation import PageNavigator
from linkedin_mcp_server.linkedin.notifications import NotificationReader
from linkedin_mcp_server.linkedin.session import PageSession

CARDS = [
    {
        "text": "Maria Jansen reacted to your post\nSnippet\n2h",
        "links": [
            {"href": "/in/maria-jansen/", "text": "Maria Jansen"},
            {"href": "/feed/update/urn:li:activity:7214916299838103554/", "text": ""},
        ],
    },
    {"text": "Sam Lee viewed your profile\n1d", "links": []},
]


async def _read(page: Any, text: str = "Notifications text", cards=None, **kwargs):
    from contextlib import ExitStack

    session = PageSession(page)
    reader = NotificationReader(
        session, PageNavigator(session), PageContentReader(session)
    )
    navigate = AsyncMock()
    scroll = AsyncMock()
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(reader._navigator, "_navigate_to_page", navigate)
        )
        stack.enter_context(patch.object(PageSession, "check_rate_limit", AsyncMock()))
        stack.enter_context(patch.object(PageSession, "dismiss_modal", AsyncMock()))
        stack.enter_context(patch.object(PageSession, "scroll_body", scroll))
        stack.enter_context(
            patch.object(
                PageSession,
                "run_on_linkedin",
                AsyncMock(return_value=CARDS if cards is None else cards),
            )
        )
        stack.enter_context(
            patch.object(
                reader._content,
                "_extract_root_content",
                AsyncMock(
                    return_value={"source": "root", "text": text, "references": []}
                ),
            )
        )
        result = await reader.get_notifications(**kwargs)
    return result, navigate, scroll


async def test_all_notifications_open_the_plain_page(mock_page):
    result, navigate, _ = await _read(mock_page)

    assert navigate.await_args.args[0] == "https://www.linkedin.com/notifications/"
    assert result["url"] == "https://www.linkedin.com/notifications/"
    assert result["filter"] == "all"
    assert [n["actor"] for n in result["notifications"] if "actor" in n] == [
        "Maria Jansen"
    ]
    assert len(result["notifications"]) == 2
    assert "sections" not in result


async def test_my_posts_opens_the_my_posts_list(mock_page):
    result, navigate, _ = await _read(mock_page, filter_by="my_posts")

    assert navigate.await_args.args[0] == (
        "https://www.linkedin.com/notifications/?filter=my_posts"
    )
    assert result["filter"] == "my_posts"


async def test_the_limit_caps_the_result_and_sizes_the_scroll(mock_page):
    result, _, scroll = await _read(mock_page, limit=1)

    assert len(result["notifications"]) == 1
    assert scroll.await_args.kwargs["max_scrolls"] == 1

    _, _, deep = await _read(mock_page, limit=45)
    assert deep.await_args.kwargs["max_scrolls"] == 5


async def test_a_page_with_no_cards_falls_back_to_its_text(mock_page):
    result, _, _ = await _read(mock_page, text="You have no notifications", cards=[])

    assert result["notifications"] == []
    assert result["sections"] == {"notifications": "You have no notifications"}


async def test_a_chrome_only_page_is_reported_as_rate_limited(mock_page):
    result, _, _ = await _read(
        mock_page,
        text="About\nAccessibility\nTalent Solutions\nCareers\nSelect language",
    )

    assert result["notifications"] == []
    assert result["section_errors"]["notifications"]["error_type"] == "rate_limit"


async def test_an_unknown_filter_is_refused_before_navigation(mock_page):
    with pytest.raises(FilterValidationError, match="filter_by"):
        await _read(mock_page, filter_by="mentions")
