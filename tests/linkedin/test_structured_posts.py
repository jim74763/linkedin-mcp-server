"""Every place that returns posts also returns them as structured items."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from linkedin_mcp_server.linkedin.capture import SectionCapture
from linkedin_mcp_server.linkedin.company import CompanyReader
from linkedin_mcp_server.linkedin.content import PageContentReader
from linkedin_mcp_server.linkedin.contracts import ExtractedSection
from linkedin_mcp_server.linkedin.link_metadata import Reference
from linkedin_mcp_server.linkedin.navigation import PageNavigator
from linkedin_mcp_server.linkedin.person import PersonReader
from linkedin_mcp_server.linkedin.posts import PostSearch
from linkedin_mcp_server.linkedin.profile_page import ProfilePageReader
from linkedin_mcp_server.linkedin.session import PageSession

# A Dutch-language page: the labels are not English, the structure is the same.
POSTS_TEXT = """\
Feed post number 1
Pat Poster
 • 1e
3 d. •
Vandaag live.
Maria en 122 anderen
7 reacties
1 repost
Vind ik leuk
Reageren
Feed post number 2
Ada Lovelace
1 w. •
Tweede bericht.
5
Vind ik leuk
Reageren
"""

REFERENCES: list[Reference] = [
    {"kind": "feed_post", "url": "/feed/update/urn:li:activity:7214916299838103554/"},
    {"kind": "feed_post", "url": "/posts/ada_x-ugcPost-7214916299838103555-AbCd"},
]


def _capture(page):
    session = PageSession(page)
    return (
        session,
        PageNavigator(session),
        SectionCapture(session, PageNavigator(session), PageContentReader(session)),
    )


def _assert_structured(posts):
    assert [p["author"] for p in posts] == ["Pat Poster", "Ada Lovelace"]
    assert posts[0]["reactions"] == 123
    assert posts[0]["comments"] == 7
    assert posts[0]["reposts"] == 1
    assert posts[0]["impressions"] is None
    assert posts[0]["url"] == (
        "https://www.linkedin.com/feed/update/urn:li:activity:7214916299838103554/"
    )
    assert posts[1]["url"] == (
        "https://www.linkedin.com/feed/update/urn:li:ugcPost:7214916299838103555/"
    )
    assert posts[1]["reactions"] == 5


async def test_a_person_profile_posts_section_gets_structured_posts(mock_page):
    session, navigator, capture = _capture(mock_page)
    reader = PersonReader(
        session,
        navigator,
        capture,
        ProfilePageReader(session, AsyncMock()),
    )
    section = ExtractedSection(text=POSTS_TEXT, references=REFERENCES)
    with (
        patch.object(capture, "capture", AsyncMock(return_value=section)),
        patch.object(PageSession, "delay", AsyncMock()),
        patch.object(
            reader._profile_page, "_extract_profile_urn", AsyncMock(return_value=None)
        ),
    ):
        result = await reader.read_person("pat-poster", {"posts"})

    _assert_structured(result["posts"])
    assert result["sections"]["posts"] == POSTS_TEXT


async def test_a_person_profile_without_posts_keeps_its_old_shape(mock_page):
    session, navigator, capture = _capture(mock_page)
    reader = PersonReader(
        session, navigator, capture, ProfilePageReader(session, AsyncMock())
    )
    with (
        patch.object(
            capture,
            "capture",
            AsyncMock(return_value=ExtractedSection(text="About text", references=[])),
        ),
        patch.object(
            reader._profile_page, "_extract_profile_urn", AsyncMock(return_value=None)
        ),
    ):
        result = await reader.read_person("pat-poster", set())

    assert "posts" not in result


async def test_a_company_posts_section_gets_structured_posts(mock_page):
    session, navigator, capture = _capture(mock_page)
    reader = CompanyReader(session, capture)
    section = ExtractedSection(text=POSTS_TEXT, references=REFERENCES)
    with (
        patch.object(capture, "capture", AsyncMock(return_value=section)),
        patch.object(PageSession, "delay", AsyncMock()),
    ):
        result = await reader.read_company("acme", {"posts"})

    _assert_structured(result["posts"])


async def test_search_posts_gets_structured_posts(mock_page):
    session, navigator, capture = _capture(mock_page)
    search = PostSearch(capture)
    section = ExtractedSection(text=POSTS_TEXT, references=REFERENCES)
    with patch.object(capture, "capture", AsyncMock(return_value=section)):
        result = await search.search_posts("acme")

    _assert_structured(result["posts"])
