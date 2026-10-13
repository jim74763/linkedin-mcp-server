"""Tests for turning notification cards into structured notifications."""

from __future__ import annotations

from typing import Any

from linkedin_mcp_server.linkedin.notification_parser import (
    classify_links,
    parse_notifications,
)

POST = "/feed/update/urn:li:activity:7214916299838103554/"


def _card(text: str, *links: tuple[str, str]) -> dict[str, Any]:
    return {"text": text, "links": [{"href": h, "text": t} for h, t in links]}


def test_a_reaction_card_names_actor_post_snippet_and_time():
    card = _card(
        "Maria Jansen\nMaria Jansen reacted to your post\n"
        "Shipping the new release today.\n2h",
        ("/in/maria-jansen/", "Maria Jansen"),
        (POST + "?updateEntityUrn=x", "Maria Jansen reacted to your post"),
    )

    [item] = parse_notifications([card])

    assert item["action_type"] == "post"
    assert item["actor"] == "Maria Jansen"
    assert item["actor_url"] == "/in/maria-jansen/"
    assert item["headline"] == "Maria Jansen reacted to your post"
    assert item["snippet"] == "Shipping the new release today."
    assert item["time"] == "2h"
    assert item["post_url"] == (
        "https://www.linkedin.com/feed/update/urn:li:activity:7214916299838103554/"
    )


def test_a_comment_card_is_told_apart_by_the_comment_urn_in_the_link():
    card = _card(
        "Sam Lee commented on your post\nGreat work.\n1d",
        ("/in/sam-lee/", "Sam Lee"),
        (
            POST + "?commentUrn=urn%3Ali%3Acomment%3A%28activity%3A1%2C2%29",
            "Sam Lee commented on your post",
        ),
    )

    [item] = parse_notifications([card])

    assert item["action_type"] == "comment"
    assert item["post_url"].endswith("urn:li:activity:7214916299838103554/")


def test_a_dutch_card_is_classified_without_reading_dutch():
    card = _card(
        "Maria Jansen heeft gereageerd op je bericht\nNieuwe release vandaag.\n3 u.",
        ("/in/maria-jansen/", "Maria Jansen"),
        (POST, "Maria Jansen heeft gereageerd op je bericht"),
    )

    [item] = parse_notifications([card])

    assert item["action_type"] == "post"
    assert item["actor"] == "Maria Jansen"
    assert item["time"] == "3 u."
    assert item["headline"] == "Maria Jansen heeft gereageerd op je bericht"


def test_the_card_chrome_does_not_leak_into_the_snippet():
    card = _card(
        "Pat Poster posted: Hiring!\nLike\nReply\n4\n5d",
        ("/in/pat-poster/", "Pat Poster • 1st"),
        (POST, "Pat Poster posted: Hiring!"),
    )

    [item] = parse_notifications([card])

    assert "snippet" not in item
    assert item["actor"] == "Pat Poster"


def test_each_link_target_maps_to_one_kind():
    kinds = {
        "/jobs/view/123/": "job",
        "/mynetwork/invitation-manager/": "invitation",
        "/company/acme/": "company",
        "/in/someone/": "profile",
        "/events/456/": "event",
        "/pulse/an-article/": "article",
        "/somewhere/else/": "other",
    }
    for href, kind in kinds.items():
        assert classify_links([{"href": href, "text": "x"}]) == kind, href


def test_a_card_with_no_text_is_skipped_and_the_rest_keep_their_order():
    cards = [
        _card(""),
        _card("A reacted\n1h", ("/in/a/", "A")),
        _card("B reacted\n2h", ("/in/b/", "B")),
    ]

    items = parse_notifications(cards)

    assert [(i["index"], i["actor"]) for i in items] == [(0, "A"), (1, "B")]


def test_a_card_without_any_link_still_gives_its_text():
    [item] = parse_notifications([_card("Your weekly summary is ready\n1w")])

    assert item["action_type"] == "other"
    assert item["headline"] == "Your weekly summary is ready"
    assert item["time"] == "1w"
    assert "actor" not in item and "url" not in item
