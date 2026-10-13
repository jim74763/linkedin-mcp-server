"""Tests for the post comment reader."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from linkedin_mcp_server.core.exceptions import InvalidReferenceError
from linkedin_mcp_server.linkedin.comments import CommentReader
from linkedin_mcp_server.linkedin.content import PageContentReader
from linkedin_mcp_server.linkedin.contracts import FilterValidationError
from linkedin_mcp_server.linkedin.navigation import PageNavigator
from linkedin_mcp_server.linkedin.session import PageSession
from linkedin_mcp_server.linkedin.ui_labels import (
    SORT_RECENT_LABELS,
    SORT_RELEVANT_LABELS,
)

PAGE = """\
Pat Poster
3d
The post.
Most relevant
Jane Roe
 • 2nd
2d
Congrats!
Like
Reply
"""

LINKS = [
    {"href": "/in/pat-poster/", "text": "Pat Poster", "left": 100},
    {"href": "/in/jane-roe/", "text": "Jane Roe", "left": 100},
]


def _reader(page: Any, text: str = PAGE) -> tuple[CommentReader, dict[str, Any]]:
    session = PageSession(page)
    navigator = PageNavigator(session)
    content = PageContentReader(session)
    reader = CommentReader(session, navigator, content)
    mocks: dict[str, Any] = {
        "navigate": AsyncMock(),
        "extract": AsyncMock(
            return_value={"source": "root", "text": text, "references": []}
        ),
        "links": AsyncMock(return_value=LINKS),
        "click": AsyncMock(return_value=False),
    }
    return reader, mocks


def _patched(reader: CommentReader, mocks: dict[str, Any]):
    return (
        patch.object(reader._navigator, "_navigate_to_page", mocks["navigate"]),
        patch.object(PageSession, "check_rate_limit", AsyncMock()),
        patch.object(PageSession, "dismiss_modal", AsyncMock()),
        patch.object(PageSession, "scroll_body", AsyncMock()),
        patch.object(PageSession, "delay", AsyncMock()),
        patch.object(PageSession, "run_on_linkedin", mocks["links"]),
        patch.object(reader._content, "_extract_root_content", mocks["extract"]),
        patch.object(reader._content, "click_button_by_text", mocks["click"]),
    )


async def _read(reader: CommentReader, mocks: dict[str, Any], *args, **kwargs):
    from contextlib import ExitStack

    with ExitStack() as stack:
        for ctx in _patched(reader, mocks):
            stack.enter_context(ctx)
        return await reader.get_post_comments(*args, **kwargs)


def _sort_clicks(mocks: dict[str, Any]) -> list[str]:
    sort_labels = {*SORT_RECENT_LABELS, *SORT_RELEVANT_LABELS}
    return [
        c.args[0] for c in mocks["click"].await_args_list if c.args[0] in sort_labels
    ]


class TestGetPostComments:
    async def test_a_url_a_urn_and_an_id_all_open_the_same_permalink(self, mock_page):
        urls = []
        for ref in (
            "https://www.linkedin.com/posts/pat-poster_launch-activity-7214916299838103554-AbCd",
            "urn:li:activity:7214916299838103554",
            "7214916299838103554",
        ):
            reader, mocks = _reader(mock_page)
            result = await _read(reader, mocks, ref)
            urls.append((result["url"], mocks["navigate"].await_args.args[0]))

        expected = (
            "https://www.linkedin.com/feed/update/urn:li:activity:7214916299838103554/"
        )
        assert urls == [(expected, expected)] * 3

    async def test_comments_are_structured_and_the_raw_text_is_not_repeated(
        self, mock_page
    ):
        reader, mocks = _reader(mock_page)

        result = await _read(reader, mocks, "7214916299838103554")

        assert result["comments"] == [
            {
                "index": 0,
                "author": "Jane Roe",
                "author_url": "/in/jane-roe/",
                "text": "Congrats!",
                "time": "2d",
                "depth": 0,
            }
        ]
        assert "sections" not in result
        assert result["post"] == {
            "kind": "activity",
            "id": "7214916299838103554",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:7214916299838103554/",
        }

    async def test_unparseable_text_is_returned_as_the_section_instead_of_dropped(
        self, mock_page
    ):
        reader, mocks = _reader(mock_page, text="Something LinkedIn rendered")
        mocks["links"].return_value = []

        result = await _read(reader, mocks, "7214916299838103554")

        assert result["comments"] == []
        assert result["sections"] == {"comments": "Something LinkedIn rendered"}

    async def test_a_chrome_only_page_is_reported_as_rate_limited(self, mock_page):
        reader, mocks = _reader(
            mock_page,
            text="About\nAccessibility\nTalent Solutions\nCareers\nSelect language",
        )

        result = await _read(reader, mocks, "7214916299838103554")

        assert result["comments"] == []
        assert result["section_errors"]["comments"]["error_type"] == "rate_limit"

    async def test_recent_sort_opens_the_control_then_picks_the_menu_item(
        self, mock_page
    ):
        reader, mocks = _reader(mock_page)
        clicked: list[tuple[str, str]] = []

        async def click(label: str, *, scope: str = "main", **_: Any) -> bool:
            clicked.append((label, scope))
            return label in {"Meest relevant", "Meest recent"}

        mocks["click"].side_effect = click
        mocks["extract"].return_value = {
            "source": "root",
            "text": PAGE.replace("Most relevant", "Meest relevant"),
            "references": [],
        }

        result = await _read(reader, mocks, "7214916299838103554", sort_by="recent")

        assert result["sort"] == {"requested": "recent", "applied": True}
        assert ("Meest relevant", "main") in clicked
        assert clicked.index(("Meest relevant", "main")) < clicked.index(
            ("Meest recent", "body")
        )

    async def test_a_sort_control_that_cannot_be_found_is_reported_not_faked(
        self, mock_page
    ):
        reader, mocks = _reader(mock_page, text="Pat Poster\n3d\nPost only")

        result = await _read(reader, mocks, "7214916299838103554", sort_by="recent")

        assert result["sort"] == {"requested": "recent", "applied": False}

    async def test_an_already_recent_list_counts_as_applied_without_a_click(
        self, mock_page
    ):
        reader, mocks = _reader(
            mock_page, text=PAGE.replace("Most relevant", "Most recent")
        )

        result = await _read(reader, mocks, "7214916299838103554", sort_by="recent")

        assert result["sort"]["applied"] is True
        assert _sort_clicks(mocks) == []

    async def test_no_sort_requested_means_no_sort_key_and_no_click_on_the_sort(
        self, mock_page
    ):
        reader, mocks = _reader(mock_page)

        result = await _read(reader, mocks, "7214916299838103554")

        assert "sort" not in result
        assert _sort_clicks(mocks) == []

    async def test_load_more_stops_at_the_first_round_that_finds_no_button(
        self, mock_page
    ):
        reader, mocks = _reader(mock_page)
        rounds = iter([True, False])

        async def click(label: str, **_: Any) -> bool:
            return label == "Load more comments" and next(rounds, False)

        mocks["click"].side_effect = click

        await _read(reader, mocks, "7214916299838103554", max_load_more=5)

        loads = [
            c
            for c in mocks["click"].await_args_list
            if c.args[0] == "Load more comments"
        ]
        assert len(loads) == 2

    async def test_a_zero_budget_never_asks_for_more(self, mock_page):
        reader, mocks = _reader(mock_page)

        await _read(reader, mocks, "7214916299838103554", max_load_more=0)

        mocks["click"].assert_not_awaited()

    async def test_an_unknown_sort_is_refused_before_any_navigation(self, mock_page):
        reader, mocks = _reader(mock_page)

        with pytest.raises(FilterValidationError, match="sort_by"):
            await _read(reader, mocks, "7214916299838103554", sort_by="oldest")

        mocks["navigate"].assert_not_awaited()

    async def test_a_reference_that_is_not_a_post_is_refused_before_navigation(
        self, mock_page
    ):
        reader, mocks = _reader(mock_page)

        with pytest.raises(InvalidReferenceError):
            await _read(reader, mocks, "https://www.linkedin.com/in/someone/")

        mocks["navigate"].assert_not_awaited()
