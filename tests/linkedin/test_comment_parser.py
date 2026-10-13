"""Tests for turning a post's comment section text into structured comments."""

from __future__ import annotations

from linkedin_mcp_server.linkedin.comment_parser import (
    Author,
    parse_comments,
    profile_slug,
)

# A post page as innerText: the post, its counters, the sort control, then three
# comments of which the last is a reply to the second. The accessible copy of
# each name ("Jane Roe" twice) is how LinkedIn renders them.
ENGLISH_PAGE = """\
Pat Poster
Pat Poster
 • 1st
Founder at Acme
3d •
Shipping the new release today.
42
7 comments
2 reposts
Like
Comment
Repost
Send
Most relevant
Jane Roe
Jane Roe
 • 2nd
Head of Product
2d
Congrats on the launch!
Like
 | 
3
Reply
Sam Lee
Sam Lee
 • 3rd+
Engineer
1d
Great work.
Second line of the comment.
Like
Reply
 | 
1 Reply
Pat Poster
Pat Poster
 • Author
Founder at Acme
5h
Thanks Sam!
Like
Reply
"""

AUTHORS: list[Author] = [
    {
        "href": "https://www.linkedin.com/in/pat-poster/",
        "text": "Pat Poster",
        "left": 100,
    },
    {"href": "https://www.linkedin.com/in/jane-roe/", "text": "", "left": 100},
    {"href": "https://www.linkedin.com/in/jane-roe/", "text": "Jane Roe", "left": 140},
    {
        "href": "https://www.linkedin.com/in/sam-lee",
        "text": "Sam Lee • 3rd+",
        "left": 140,
    },
    {"href": "/in/pat-poster/?miniProfileUrn=x", "text": "Pat Poster", "left": 200},
]


def test_each_comment_is_split_out_with_its_author_and_time():
    comments = parse_comments(ENGLISH_PAGE, AUTHORS)

    assert [c["author"] for c in comments] == ["Jane Roe", "Sam Lee", "Pat Poster"]
    assert [c["author_url"] for c in comments] == [
        "/in/jane-roe/",
        "/in/sam-lee/",
        "/in/pat-poster/",
    ]
    assert [c.get("time") for c in comments] == ["2d", "1d", "5h"]


def test_the_post_above_the_sort_control_is_not_a_comment():
    comments = parse_comments(ENGLISH_PAGE, AUTHORS)

    assert "Shipping the new release today." not in " ".join(
        c["text"] for c in comments
    )
    assert len(comments) == 3


def test_the_action_row_is_trimmed_but_a_multi_line_body_is_kept():
    comments = parse_comments(ENGLISH_PAGE, AUTHORS)

    assert comments[0]["text"] == "Congrats on the launch!"
    assert comments[1]["text"] == "Great work.\nSecond line of the comment."
    assert comments[2]["text"] == "Thanks Sam!"


def test_indentation_gives_nesting_and_the_parent_comment():
    comments = parse_comments(ENGLISH_PAGE, AUTHORS)

    assert [c["depth"] for c in comments] == [0, 0, 1]
    assert comments[2]["reply_to"] == 1
    assert "reply_to" not in comments[0]


def test_without_positions_nesting_is_left_out_not_guessed():
    flat: list[Author] = [{"href": a["href"], "text": a["text"]} for a in AUTHORS]

    comments = parse_comments(ENGLISH_PAGE, flat)

    assert len(comments) == 3
    assert all("depth" not in c and "reply_to" not in c for c in comments)


def test_a_dutch_page_parses_on_shape_and_not_on_english_words():
    page = """\
Pat Poster
 • 1e
3 dagen
Nieuwe release vandaag.
42
7 reacties
Vind ik leuk
Reageren
Meest relevant
Jane Roe
 • 2e
Productmanager
2 d.
Gefeliciteerd met de lancering!
Vind ik leuk
 | 
3
Reageren
Sam Lee
 • 3e+
1 u.
Mooi werk.
Vind ik leuk
Reageren
 | 
1 antwoord
"""
    authors: list[Author] = [
        {"href": "/in/pat-poster/", "text": "Pat Poster"},
        {"href": "/in/jane-roe/", "text": "Jane Roe"},
        {"href": "/in/sam-lee/", "text": "Sam Lee"},
    ]

    comments = parse_comments(page, authors)

    assert [c["author"] for c in comments] == ["Jane Roe", "Sam Lee"]
    assert [c["time"] for c in comments] == ["2 d.", "1 u."]
    assert [c["text"] for c in comments] == [
        "Gefeliciteerd met de lancering!",
        "Mooi werk.",
    ]


def test_without_a_sort_control_the_posts_own_header_is_skipped():
    page = """\
Pat Poster
3d
The post body.
5
Like
Jane Roe
 • 2nd
2d
First!
Like
Reply
"""
    authors: list[Author] = [
        {"href": "/in/pat-poster/", "text": "Pat Poster"},
        {"href": "/in/jane-roe/", "text": "Jane Roe"},
    ]

    comments = parse_comments(page, authors)

    assert [c["author"] for c in comments] == ["Jane Roe"]
    assert comments[0]["text"] == "First!"


def test_mention_links_between_two_authors_do_not_hide_the_next_comment():
    page = """\
Pat Poster
Most relevant
Jane Roe
2d
Thanks for the intro to Zed, Yan, Xia, Wim and Val
Like
Sam Lee
1d
Agreed.
Like
"""
    mentions = ["zed", "yan", "xia", "wim", "val"]
    authors: list[Author] = [
        {"href": "/in/pat-poster/", "text": "Pat Poster"},
        {"href": "/in/jane-roe/", "text": "Jane Roe"},
        *[Author(href=f"/in/{slug}/", text=slug.title()) for slug in mentions],
        {"href": "/in/sam-lee/", "text": "Sam Lee"},
    ]

    comments = parse_comments(page, authors)

    assert [c["author"] for c in comments] == ["Jane Roe", "Sam Lee"]
    assert comments[1]["text"] == "Agreed."


def test_nothing_to_structure_gives_an_empty_list():
    assert parse_comments("", []) == []
    assert parse_comments("Some text without authors", []) == []


def test_profile_slug_reads_absolute_and_relative_links():
    assert profile_slug("https://www.linkedin.com/in/jane-roe/?x=1") == "jane-roe"
    assert profile_slug("/in/jane-roe") == "jane-roe"
    assert profile_slug("/company/acme/") is None
