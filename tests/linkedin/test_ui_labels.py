"""Tests for the locale-aware line shapes and label tables."""

from __future__ import annotations

import pytest

from linkedin_mcp_server.linkedin.ui_labels import (
    count_label,
    is_action_label,
    is_degree_badge,
    is_relative_time,
    parse_count,
    parse_degree,
    reaction_total,
    relative_time_text,
)


@pytest.mark.parametrize(
    "line",
    [
        "2h",
        "3 w.",
        "5 min",
        "1mo",
        "2 uur",
        "3 weken geleden",
        "4d • Edited",
        "now",
        "Zojuist",
    ],
)
def test_relative_times_are_recognised_by_shape(line):
    assert is_relative_time(line)


@pytest.mark.parametrize(
    "line",
    [
        "45 comments",
        "7 reacties",
        "1,234 impressions",
        "Congrats on the launch!",
        "2024 was a great year for us",
        "",
        "• 2nd",
    ],
)
def test_counts_and_prose_are_not_times(line):
    assert not is_relative_time(line)


def test_the_time_drops_the_bullet_tail():
    assert relative_time_text("4d • Edited •") == "4d"
    assert relative_time_text("2 weken") == "2 weken"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("• 1st", (1, False)),
        ("• 2e", (2, False)),
        (" · 3rd+", (3, True)),
        ("• 3e+", (3, True)),
        ("2nd", (2, False)),
        ("• Author", None),
        ("Engineer", None),
    ],
)
def test_degree_badges_read_the_digit_not_the_word(line, expected):
    assert parse_degree(line) == expected


def test_a_headline_with_a_digit_is_not_a_badge():
    assert not is_degree_badge("2 years at Acme")
    assert is_degree_badge("• 2nd")


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("12", 12),
        ("1,234", 1234),
        ("1.234", 1234),
        ("1 234", 1234),
        ("1.2K", 1200),
        ("1,2K", 1200),
        ("3M", 3_000_000),
        ("x", None),
        ("", None),
    ],
)
def test_counts_parse_across_separator_styles(token, expected):
    assert parse_count(token) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("45 comments", ("comments", 45)),
        ("7 reacties", ("comments", 7)),
        ("3 reposts", ("reposts", 3)),
        ("1.234 weergaven", ("impressions", 1234)),
        ("2 Impressionen", ("impressions", 2)),
        ("1 Reply", ("replies", 1)),
        ("2 antwoorden", ("replies", 2)),
        ("15,000 followers", ("followers", 15000)),
        ("500 volgers", ("followers", 500)),
        ("5 people like this", None),
        ("2024 results", None),
    ],
)
def test_count_labels_need_the_whole_remainder_to_be_a_label(line, expected):
    assert count_label(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("123", 123),
        ("1,234", 1234),
        ("Maria and 122 others", 123),
        ("Maria en 122 anderen", 123),
        ("Maria und 5 weitere", 6),
        ("Congrats on the launch", None),
    ],
)
def test_reaction_total_counts_the_named_person_too(line, expected):
    assert reaction_total(line) == expected


def test_action_labels_cover_several_languages():
    assert is_action_label("Reply")
    assert is_action_label("Reageren")
    assert is_action_label("Gefällt mir")
    assert not is_action_label("Replying to a long thread")
