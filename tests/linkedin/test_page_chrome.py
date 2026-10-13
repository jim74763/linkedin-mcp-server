"""Page chrome cleanup: footers, language pickers, modules, promoted posts."""

from __future__ import annotations

import pytest

from linkedin_mcp_server.linkedin.text import (
    filter_linkedin_noise_lines,
    strip_linkedin_noise,
    truncate_linkedin_noise,
)

PICKER = "English (English)\nNederlands (Dutch)\nDeutsch (German)\nFrançais (French)\n"


def test_dutch_footer_is_cut():
    text = "Real content\nMore\n\nOver\nToegankelijkheid\nTalent Solutions\nPrivacy"
    assert truncate_linkedin_noise(text) == "Real content\nMore"


@pytest.mark.parametrize(
    "first,second",
    [
        ("Info", "Barrierefreiheit"),
        ("À propos", "Accessibilité"),
        ("Sobre", "Acessibilidade"),
    ],
)
def test_footer_pair_in_other_locales(first, second):
    text = f"Body line\n{first}\n{second}\nrest of footer"
    assert truncate_linkedin_noise(text) == "Body line"


def test_single_footer_word_is_kept():
    text = "Body\nOver\nSomething else entirely"
    assert truncate_linkedin_noise(text) == text


def test_language_picker_is_cut():
    text = "Body\nwith words\n" + PICKER + "Select language"
    assert truncate_linkedin_noise(text) == "Body\nwith words"


def test_single_parenthesis_line_is_kept():
    text = "Body\nEnglish (English)\nmore body"
    assert truncate_linkedin_noise(text) == text


def test_copyright_line_is_cut():
    text = "Body\nLinkedIn Corporation © 2026\n"
    assert truncate_linkedin_noise(text) == "Body"


def test_recommendation_heading_ends_plain_page():
    text = "Profile\nAbout me\nPeople you may know\nSomeone\nSomeone else"
    assert truncate_linkedin_noise(text) == "Profile\nAbout me"


def test_dutch_recommendation_heading_ends_plain_page():
    text = "Profiel\nMensen die je misschien kent\nIemand"
    assert truncate_linkedin_noise(text) == "Profiel"


FEED = """Feed post number 1
Ann Author
Hello world
Like
Feed post number 2
Mensen die je misschien kent
Bob
Connect
Cara
Connect
Feed post number 3
Dan Writer
Promoted
Buy our thing
Feed post number 4
Eve Real
Another real post
Promoted by nobody mentioned in the body
"""


def test_module_between_posts_is_removed_and_promoted_post_dropped():
    out = truncate_linkedin_noise(FEED)
    assert "Bob" not in out
    assert "Cara" not in out
    assert "Buy our thing" not in out
    assert "Hello world" in out
    assert "Another real post" in out
    # The headings of the kept posts and of the post holding the module stay.
    assert "Feed post number 1" in out
    assert "Feed post number 4" in out


def test_promoted_word_deep_in_a_post_is_not_a_label():
    lines = ["Feed post number 1", "A", "B", "C", "D", "E", "F", "G", "H", "I"]
    text = "\n".join(lines + ["Promoted", "end"])
    assert "Promoted" in truncate_linkedin_noise(text)


def test_promoted_label_outside_feed_text_is_untouched():
    text = "Software engineer\nAcme\nPromoted\nApply"
    assert truncate_linkedin_noise(text) == text


def test_recommendation_before_first_post_is_cut_up_to_the_post():
    text = "People you may know\nBob\nFeed post number 1\nHi"
    assert truncate_linkedin_noise(text) == "Feed post number 1\nHi"


def test_filter_compacts_whitespace():
    text = "Line one   \n\n\n\n • \n|\nLine two\n\n"
    assert filter_linkedin_noise_lines(text) == "Line one\n\nLine two"


def test_strip_is_smaller_on_a_noisy_page():
    body = "Hello\n" * 5
    noisy = body + "\n\n\nOver\nToegankelijkheid\n" + PICKER
    cleaned = strip_linkedin_noise(noisy)
    assert len(cleaned) < len(noisy) / 2
    assert cleaned.startswith("Hello")
