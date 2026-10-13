"""Tests for post reference normalization."""

from __future__ import annotations

import pytest

from linkedin_mcp_server.core.exceptions import InvalidReferenceError
from linkedin_mcp_server.linkedin.identifiers import (
    normalize_post_reference,
    post_update_url,
)

ID = "7214916299838103554"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (ID, ("activity", ID)),
        (f"urn:li:activity:{ID}", ("activity", ID)),
        (f"urn:li:ugcPost:{ID}", ("ugcPost", ID)),
        (f"urn:li:share:{ID}", ("share", ID)),
        (
            f"https://www.linkedin.com/feed/update/urn:li:activity:{ID}/",
            ("activity", ID),
        ),
        (
            f"https://www.linkedin.com/feed/update/urn%3Ali%3AugcPost%3A{ID}/?utm=x",
            ("ugcPost", ID),
        ),
        (f"/feed/update/urn:li:share:{ID}/", ("share", ID)),
        (
            f"https://www.linkedin.com/posts/pat-poster_launch-day-activity-{ID}-AbCd?rcm=1",
            ("activity", ID),
        ),
        (f"/posts/pat_x-ugcPost-{ID}-ZzZz", ("ugcPost", ID)),
        (f"  {ID}  ", ("activity", ID)),
    ],
)
def test_every_shape_of_a_post_reference_resolves(value, expected):
    assert normalize_post_reference(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "12345",
        "https://www.linkedin.com/in/someone/",
        f"https://example.com/feed/update/urn:li:activity:{ID}/",
        "urn:li:fsd_profile:ACoAAB",
        f"../../feed/{ID}\\x",
    ],
)
def test_anything_else_is_refused(value):
    with pytest.raises(InvalidReferenceError):
        normalize_post_reference(value)


def test_the_permalink_is_rebuilt_from_the_kind_and_id_only():
    assert (
        post_update_url("ugcPost", ID)
        == f"https://www.linkedin.com/feed/update/urn:li:ugcPost:{ID}/"
    )
    with pytest.raises(InvalidReferenceError):
        post_update_url("activity", "12/../x")
    with pytest.raises(InvalidReferenceError):
        post_update_url("profile", ID)
