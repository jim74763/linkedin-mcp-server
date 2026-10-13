"""Tests for structuring a list of posts out of their rendered text."""

from __future__ import annotations

from linkedin_mcp_server.linkedin.post_parser import (
    parse_posts,
    structured_posts,
    with_posts,
)

ENGLISH = """\
Feed post number 1
Pat Poster
Pat Poster
 • 1st
Founder at Acme
3d •
Follow
Shipping the new release today.
Second paragraph of the post.
…more
1,234 impressions
42
7 comments
2 reposts
Like
Comment
Repost
Send
Feed post number 2
Acme Inc
15,000 followers
1w • Edited •
Hiring: two engineers.
Maria and 122 others
Like
Comment
Repost
Send
"""

DUTCH = """\
Feed post number 1
Pat Poster
 • 1e
Oprichter bij Acme
3 d. •
Volgen
Vandaag live.
…meer weergeven
Maria en 122 anderen
7 reacties
1 repost
Vind ik leuk
Reageren
Repost
Verzenden
"""


def test_each_post_is_split_with_author_time_and_text():
    posts = parse_posts(ENGLISH)

    assert [p["author"] for p in posts] == ["Pat Poster", "Acme Inc"]
    assert [p["time"] for p in posts] == ["3d", "1w"]
    assert (
        posts[0]["text"]
        == "Shipping the new release today.\nSecond paragraph of the post."
    )
    assert posts[1]["text"] == "Hiring: two engineers."


def test_counts_are_separate_labelled_fields_not_raw_text():
    first, second = parse_posts(ENGLISH)

    assert (
        first["reactions"],
        first["comments"],
        first["reposts"],
        first["impressions"],
    ) == (
        42,
        7,
        2,
        1234,
    )
    # "Maria and 122 others" is the named person plus 122 others.
    assert (second["reactions"], second["comments"], second["reposts"]) == (
        123,
        None,
        None,
    )
    assert second["impressions"] is None
    assert "impressions" not in first["text"] and "comments" not in first["text"]


def test_a_dutch_post_gets_the_same_fields_from_its_own_words():
    [post] = parse_posts(DUTCH)

    assert post["author"] == "Pat Poster"
    assert post["time"] == "3 d."
    assert post["text"] == "Vandaag live."
    assert (post["reactions"], post["comments"], post["reposts"]) == (123, 7, 1)


def test_without_headings_a_run_of_action_buttons_ends_each_post():
    text = "\n".join(
        [
            "Pat Poster",
            "3d",
            "First post body.",
            "5",
            "Like",
            "Comment",
            "Repost",
            "Ada Lovelace",
            "1w",
            "Second post body.",
            "2 comments",
            "Like",
            "Comment",
        ]
    )

    posts = parse_posts(text)

    assert [p["author"] for p in posts] == ["Pat Poster", "Ada Lovelace"]
    assert posts[0]["reactions"] == 5
    assert posts[1]["comments"] == 2


def test_text_with_no_post_structure_yields_no_posts():
    assert parse_posts("Some profile text\nwith no posts") == []
    assert parse_posts("") == []


def test_permalinks_attach_in_order_when_the_counts_agree():
    refs = [
        {
            "kind": "feed_post",
            "url": "/feed/update/urn:li:activity:7214916299838103554/",
        },
        {
            "kind": "feed_post",
            "url": "/posts/acme_hiring-ugcPost-7214916299838103555-AbCd",
        },
        {"kind": "person", "url": "/in/pat-poster/"},
    ]

    posts = structured_posts(ENGLISH, refs)

    assert [p["url"] for p in posts] == [
        "https://www.linkedin.com/feed/update/urn:li:activity:7214916299838103554/",
        "https://www.linkedin.com/feed/update/urn:li:ugcPost:7214916299838103555/",
    ]
    assert [p["activity_id"] for p in posts] == [
        "7214916299838103554",
        "7214916299838103555",
    ]


def test_the_two_url_shapes_of_one_post_count_once():
    refs = [
        {
            "kind": "feed_post",
            "url": "/feed/update/urn:li:activity:7214916299838103554/",
        },
        {"kind": "feed_post", "url": "/posts/pat_x-activity-7214916299838103554-AbCd"},
        {
            "kind": "feed_post",
            "url": "/feed/update/urn:li:activity:7214916299838103555/",
        },
    ]

    posts = structured_posts(ENGLISH, refs)

    assert [p["activity_id"] for p in posts] == [
        "7214916299838103554",
        "7214916299838103555",
    ]


def test_a_permalink_count_that_does_not_match_leaves_every_url_off():
    refs = [
        {
            "kind": "feed_post",
            "url": "/feed/update/urn:li:activity:7214916299838103554/",
        },
    ]

    posts = structured_posts(ENGLISH, refs)

    assert len(posts) == 2
    assert all("url" not in p for p in posts)


def test_with_posts_adds_the_key_only_when_posts_were_found():
    found = with_posts({"url": "u", "sections": {"posts": ENGLISH}}, "posts")
    other = with_posts({"url": "u", "sections": {"posts": "Nothing here"}}, "posts")
    missing = with_posts({"url": "u", "sections": {}}, "posts")

    assert len(found["posts"]) == 2
    assert "posts" not in other
    assert "posts" not in missing


def test_a_follower_count_in_the_header_is_not_mistaken_for_the_time():
    text = "\n".join(
        [
            "Feed post number 1",
            "Acme Inc",
            "500 followers",
            "2w •",
            "Body.",
            "Like",
            "Comment",
        ]
    )

    [post] = parse_posts(text)

    assert post["time"] == "2w"
    assert post["text"] == "Body."
