"""
LinkedIn notifications reading tool.

Reads the notifications page and returns each card as a structured item. The
kind of a notification comes from where its links lead, not from its words, so
it holds in every interface language.
"""

import logging
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from linkedin_mcp_server.config.schema import DEFAULT_TOOL_TIMEOUT_SECONDS
from linkedin_mcp_server.core.exceptions import AuthenticationError
from linkedin_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from linkedin_mcp_server.error_handler import raise_tool_error
from linkedin_mcp_server.linkedin.contracts import FilterValidationError

logger = logging.getLogger(__name__)


def register_notification_tools(
    mcp: FastMCP, *, tool_timeout: float = DEFAULT_TOOL_TIMEOUT_SECONDS
) -> None:
    """Register notification tools with the MCP server."""

    @mcp.tool(
        timeout=tool_timeout,
        title="Get Notifications",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"notifications"},
    )
    async def get_notifications(
        ctx: Context,
        filter_by: Literal["all", "my_posts"] = "all",
        limit: Annotated[int, Field(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        """
        Get the authenticated user's LinkedIn notifications.

        Args:
            ctx: FastMCP context for progress reporting
            filter_by: "all" for every notification (default), or "my_posts"
                for the "My posts" list: reactions, comments and reposts on the
                user's own posts.
            limit: Maximum number of notifications to return (1-100, default
                30). The page is scrolled far enough to load about that many.

        Returns:
            Dict with url, filter and notifications: a list of {index,
            action_type, headline} plus actor and actor_url (relative
            /in/<slug>/ path), snippet (the post or comment text shown on the
            card), time (as LinkedIn shows it, e.g. "2h"), post_url (canonical
            permalink of the post the card opens) and url (where the card
            links). action_type is read from where the card links, so it does
            not depend on the interface language: "comment" (a comment on a
            post), "post" (a reaction, mention or repost; the verb is in
            headline), "invitation", "job", "event", "article", "company",
            "profile" or "other". sections["notifications"] holds the cleaned
            page text only when no card could be structured.
        """
        try:
            extractor = await get_ready_extractor(ctx, tool_name="get_notifications")
            logger.info(
                "Reading notifications (filter_by=%s, limit=%d)", filter_by, limit
            )

            await ctx.report_progress(
                progress=0, total=100, message="Reading notifications"
            )

            try:
                result = await extractor.get_notifications(filter_by, limit)
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
                raise_tool_error(relogin_exc, "get_notifications")
        except Exception as e:
            raise_tool_error(e, "get_notifications")  # NoReturn
