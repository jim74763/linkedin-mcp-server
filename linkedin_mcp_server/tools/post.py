"""
LinkedIn post/content search tool.

Performs LinkedIn's global content search (the "Posts" results tab) using
innerText extraction, so informal "we're hiring" / "Buscamos ..." posts can
be found before a formal job listing is published. Mirrors search_people:
build a /search/results/content/ URL, scroll to load results, and return the
raw innerText for the LLM to parse, plus post-permalink references.
"""

import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from linkedin_mcp_server.config.schema import DEFAULT_TOOL_TIMEOUT_SECONDS
from linkedin_mcp_server.core.exceptions import AuthenticationError
from linkedin_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from linkedin_mcp_server.error_handler import raise_tool_error
from linkedin_mcp_server.linkedin.comment_parser import COMMENT_SORTS
from linkedin_mcp_server.linkedin.contracts import FilterValidationError
from linkedin_mcp_server.linkedin.identifiers import normalize_post_reference

logger = logging.getLogger(__name__)


def register_post_tools(
    mcp: FastMCP, *, tool_timeout: float = DEFAULT_TOOL_TIMEOUT_SECONDS
) -> None:
    """Register post/content-search tools with the MCP server."""

    @mcp.tool(
        timeout=tool_timeout,
        title="Search Posts",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"post", "search"},
    )
    async def search_posts(
        keywords: str,
        ctx: Context,
        date_posted: str | None = None,
        max_pages: Annotated[int, Field(ge=1, le=10)] = 3,
    ) -> dict[str, Any]:
        """
        Search LinkedIn posts/content globally by keyword (the "Posts" tab).

        Use this to catch informal hiring posts ("we're hiring", "Buscamos
        ...", "estamos contratando", "join our team") that often appear before
        a formal job listing exists. This is global content search, distinct
        from get_feed (your own home feed) and get_company_posts (one
        company's page).

        Args:
            keywords: Search keywords (e.g., "Buscamos Unity", "AI automation hiring")
            ctx: FastMCP context for progress reporting
            date_posted: Optional recency filter. One of "past-24h",
                "past-week", "past-month"; the "past_24_hours" / "past_week" /
                "past_month" spellings used by search_jobs are accepted too.
                Omit for any time.
            max_pages: Scroll depth as result "pages" of ~5 scrolls each
                (1-10, default 3). Content search is an infinite scroll, so
                this caps how far the page is scrolled rather than fetching
                discrete pages.

        Returns:
            Dict with url, sections (search_results -> raw text), and optional
            references (post authors, companies, linked jobs, and kind
            "feed_post" permalinks read from the page's payload responses —
            /feed/update/<urn>/ or /posts/<slug>, both valid permalinks) and
            section_errors. The DOM carries no per-post permalink anchors;
            captured permalinks are not aligned to result order. Also posts:
            each post as {index, text, reactions, comments, reposts,
            impressions} plus author, time and, only when the page gave
            exactly one permalink per post, url and activity_id. The counts
            are integers, or null when the post does not show them. The LLM
            may still read the raw text for headline/role and company.
        """
        try:
            extractor = await get_ready_extractor(ctx, tool_name="search_posts")
            logger.info(
                "Searching posts: keywords='%s', date_posted='%s', max_pages=%d",
                keywords,
                date_posted,
                max_pages,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Starting post search"
            )

            try:
                result = await extractor.search_posts(
                    keywords,
                    date_posted=date_posted,
                    max_pages=max_pages,
                )
            except FilterValidationError as e:
                # Validation messages carry actionable detail; surface them as
                # ToolError so mask_error_details doesn't reduce them to a
                # generic "Error calling tool 'search_posts'".
                raise ToolError(str(e)) from e

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except ToolError:
            # Already a properly formatted client-facing error; do not log it
            # as "Unexpected error" via raise_tool_error.
            raise
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "search_posts")
        except Exception as e:
            raise_tool_error(e, "search_posts")  # NoReturn

    @mcp.tool(
        timeout=tool_timeout,
        title="Get Post Comments",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"post"},
    )
    async def get_post_comments(
        post: str,
        ctx: Context,
        sort_by: str | None = None,
        max_load_more: Annotated[int, Field(ge=0, le=10)] = 3,
    ) -> dict[str, Any]:
        """
        Get the comments on a LinkedIn post.

        Args:
            post: The post to read: its URL (``/feed/update/urn:li:activity:<id>/``
                or ``/posts/<slug>``), its activity URN, or the numeric activity id.
            ctx: FastMCP context for progress reporting
            sort_by: "recent" for most recent first, "relevant" for most relevant
                first. Omit to keep LinkedIn's default order. The sort control
                is found by its visible label, so check sort.applied in the
                result: when it is false the comments are in LinkedIn's
                default order.
            max_load_more: How many times to ask LinkedIn for more comments
                (0-10, default 3).

        Returns:
            Dict with url, post ({kind, id, url}), optional sort
            ({requested, applied}) and comments: a list of {index, author,
            author_url, text} plus time (as LinkedIn shows it, e.g. "2w"),
            depth and reply_to (index of the parent comment) when the page
            showed the nesting. Replies LinkedIn collapses behind a "load
            replies" control are not expanded. sections["comments"] holds the
            cleaned page text only when no comment could be structured.
        """
        try:
            # Both checks run before the readiness call, which can install
            # Chromium or rotate a login for an argument that was never usable.
            normalize_post_reference(post)
            if sort_by is not None and sort_by not in COMMENT_SORTS:
                raise ToolError(
                    f"sort_by must be one of {', '.join(COMMENT_SORTS)}; got {sort_by!r}"
                )
            extractor = await get_ready_extractor(ctx, tool_name="get_post_comments")
            logger.info(
                "Reading post comments: post='%s', sort_by=%s, max_load_more=%d",
                post,
                sort_by,
                max_load_more,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Reading post comments"
            )

            try:
                result = await extractor.get_post_comments(
                    post, sort_by=sort_by, max_load_more=max_load_more
                )
            except FilterValidationError as e:
                raise ToolError(str(e)) from e

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except ToolError:
            raise
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_post_comments")
        except Exception as e:
            raise_tool_error(e, "get_post_comments")  # NoReturn
