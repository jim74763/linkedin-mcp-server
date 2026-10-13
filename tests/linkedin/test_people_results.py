"""Structured people from a people search page."""

from __future__ import annotations

from linkedin_mcp_server.linkedin.comment_parser import Author
from linkedin_mcp_server.linkedin.people_results import parse_people

TEXT_EN = """Maria Jansen
• 2nd
Product Manager at Acme
Amsterdam, North Holland, Netherlands
Connect
Pieter de Vries
• 3rd+
Engineer
Utrecht
Message
"""

LINKS: list[Author] = [
    {"href": "/in/maria-jansen/", "text": ""},
    {"href": "/in/maria-jansen/", "text": "Maria Jansen"},
    {"href": "/in/pieter-dv", "text": "Pieter de Vries • 3rd+"},
]


def test_two_cards_in_english():
    people = parse_people(TEXT_EN, LINKS)
    assert people == [
        {
            "name": "Maria Jansen",
            "profile_slug": "maria-jansen",
            "profile_url": "/in/maria-jansen/",
            "connection_degree": 2,
            "headline": "Product Manager at Acme",
            "location": "Amsterdam, North Holland, Netherlands",
        },
        {
            "name": "Pieter de Vries",
            "profile_slug": "pieter-dv",
            "profile_url": "/in/pieter-dv/",
            "connection_degree": 3,
            "connection_degree_or_more": True,
            "headline": "Engineer",
            "location": "Utrecht",
        },
    ]


def test_dutch_card_with_inline_degree_and_button():
    text = (
        "Sanne Bakker • 1e\n"
        "Marketingmanager bij Foo\n"
        "Rotterdam, Zuid-Holland, Nederland\n"
        "Bericht\n"
        "Tim Smit • 2e\n"
        "Verbinden\n"
    )
    links: list[Author] = [
        {"href": "/in/sanne/", "text": "Sanne Bakker"},
        {"href": "/in/tim/", "text": "Tim Smit"},
    ]
    people = parse_people(text, links)
    assert people[0]["connection_degree"] == 1
    assert people[0]["headline"] == "Marketingmanager bij Foo"
    assert people[0]["location"] == "Rotterdam, Zuid-Holland, Nederland"
    # A card that goes straight to its buttons has no headline or location.
    assert people[1] == {
        "name": "Tim Smit",
        "profile_slug": "tim",
        "profile_url": "/in/tim/",
        "connection_degree": 2,
    }


def test_button_ends_the_facts():
    text = "A B\n• 2nd\nHeadline\nConnect\nShared connection line\n"
    people = parse_people(text, [{"href": "/in/ab/", "text": "A B"}])
    assert people[0]["headline"] == "Headline"
    assert "location" not in people[0]


def test_repeated_member_is_listed_once():
    text = "A B\n• 2nd\nH\nL\nA B\n• 2nd\nH\nL\n"
    links: list[Author] = [
        {"href": "/in/ab/", "text": "A B"},
        {"href": "/in/ab/", "text": "A B"},
    ]
    assert len(parse_people(text, links)) == 1


def test_no_links_or_no_text_gives_nothing():
    assert parse_people("", LINKS) == []
    assert parse_people(TEXT_EN, []) == []
    assert parse_people("nothing about anyone", LINKS) == []
