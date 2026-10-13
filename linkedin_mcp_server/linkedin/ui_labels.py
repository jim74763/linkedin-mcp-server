"""Line shapes and per-locale label tables for reading rendered LinkedIn text.

The account language, not the browser, decides which language LinkedIn renders:
a document served to a context forced to en-US still arrives in German or Dutch
for a member who picked that language (see the ``lang="de"`` document in
``tests/fixtures/linkedin``). Classification that reads visible words therefore
has to know more than English.

Two kinds of signal live here, and they are kept apart on purpose:

- **Shapes** need no table. A relative time is a small number followed by a
  short unit word, a degree badge is a bullet and a digit, a count is a number.
  They are matched on that structure, whatever the unit word is.
- **Labels** are words with no structural tell: the name of a button, the noun
  after a count. For those the only signal is the text, so they sit in explicit
  per-locale tables (AGENTS.md, LinkedIn Page Rules). A language missing from a
  table reads as "no label matched", never as a guess.

The non-English entries were written from the languages LinkedIn ships and have
not all been measured against a live page; ``MEASURED`` names the locales whose
strings were checked. An unmeasured entry can only fail to match, it cannot
mislabel, because every table is matched as a whole word or a whole line.
"""

from __future__ import annotations

import re

#: Locales whose entries below were read off a live page. The rest are
#: best-effort translations of the same UI strings.
MEASURED = frozenset({"en"})


def non_empty_lines(text: str) -> list[str]:
    """The stripped, non-empty lines of *text*."""
    return [line.strip() for line in text.splitlines() if line.strip()]


# --- Shapes ------------------------------------------------------------------

# "2h", "3 w.", "5 min", "1mo", "2 uur", "3 weken geleden", "4d • Edited".
# A number up to three digits, then one to three short alphabetic words, then an
# optional bullet and whatever LinkedIn appends after it. What it must not be is
# a count ("45 comments"), which the callers rule out with ``count_label``.
_RELATIVE_TIME = re.compile(
    r"^(?P<n>\d{1,3})\s?(?P<unit>[^\W\d_]{1,12}\.?(?:\s[^\W\d_]{1,12}\.?){0,2})"
    r"(?:\s*[•·].*)?$"
)

# "Now" has no number. Worth a table entry because a comment posted seconds ago
# is the one a sort-by-recent caller most wants.
_JUST_NOW = frozenset(
    {"now", "just now", "nu", "zojuist", "jetzt", "gerade eben", "maintenant"}
)

#: The bullet LinkedIn puts between name, degree and time.
_BULLETS = "•·"

# "• 2nd", "• 2e", "· 3rd+", "•  1." : a bullet then a digit and a short suffix.
_DEGREE = re.compile(
    rf"^[{_BULLETS}]?\s*(?P<d>[1-3])(?P<plus>\+)?\s?(?:st|nd|rd|th|e|de|er|ème|ste|º|°|\.)?"
    r"(?P<more>\+)?$"
)


def is_relative_time(line: str) -> bool:
    """Whether *line* reads as a relative time such as ``2w`` or ``3 weken``."""
    stripped = line.strip()
    if stripped.lower() in _JUST_NOW:
        return True
    match = _RELATIVE_TIME.match(stripped)
    if match is None:
        return False
    # A count is "<number> <label>", never a time, and reading it as one would
    # cut a comment's body at the first "3 replies".
    return count_label(stripped) is None


def relative_time_text(line: str) -> str:
    """The time part of a time line, without the bullet tail (``2w • Edited``)."""
    return re.split(rf"\s*[{_BULLETS}]", line.strip(), maxsplit=1)[0].strip()


def parse_degree(line: str) -> tuple[int, bool] | None:
    """A connection-degree badge as ``(degree, or_more)``, or ``None``.

    Read from the digit alone: ``2nd``, ``2e``, ``2.`` and ``2º`` are all the
    second degree. ``or_more`` marks the ``3rd+`` form, LinkedIn's "third degree
    or beyond".
    """
    match = _DEGREE.match(line.strip())
    if match is None:
        return None
    return int(match.group("d")), bool(match.group("plus") or match.group("more"))


def is_degree_badge(line: str) -> bool:
    """Whether *line* is only a connection-degree badge."""
    stripped = line.strip()
    if not stripped or parse_degree(stripped) is None:
        return False
    return stripped[0] in _BULLETS or len(stripped) <= 4


# --- Counts ------------------------------------------------------------------

# The noun that follows a count, as stems matched against the whole word. One
# row per language keeps a missing language visible instead of implicit.
_COUNT_LABELS: dict[str, dict[str, tuple[str, ...]]] = {
    "comments": {
        "en": ("comment", "comments"),
        "nl": ("reactie", "reacties", "opmerking", "opmerkingen"),
        "de": ("kommentar", "kommentare"),
        "fr": ("commentaire", "commentaires"),
        "es": ("comentario", "comentarios"),
        "it": ("commento", "commenti"),
        "pt": ("comentário", "comentários", "comentario", "comentarios"),
    },
    "reposts": {
        "en": ("repost", "reposts", "share", "shares"),
        "nl": ("repost", "reposts", "keer gedeeld", "deling", "delingen"),
        "de": ("repost", "reposts", "mal geteilt", "weitergeleitet"),
        "fr": ("republication", "republications", "partage", "partages"),
        "es": ("publicación compartida", "veces compartido", "compartido"),
        "it": ("repost", "condivisione", "condivisioni"),
        "pt": ("compartilhamento", "compartilhamentos", "partilha", "partilhas"),
    },
    "impressions": {
        "en": ("impression", "impressions"),
        "nl": ("impressie", "impressies", "weergave", "weergaven", "vertoningen"),
        "de": ("impression", "impressionen"),
        "fr": ("impression", "impressions"),
        "es": ("impresión", "impresiones"),
        "it": ("impressione", "impressioni"),
        "pt": ("impressão", "impressões", "impressao", "impressoes"),
    },
    "reactions": {
        "en": ("reaction", "reactions", "like", "likes"),
        "nl": ("likes",),
        "de": ("reaktion", "reaktionen"),
        "fr": ("réaction", "réactions"),
        "es": ("reacción", "reacciones"),
        "it": ("reazione", "reazioni"),
        "pt": ("reação", "reações", "reacao", "reacoes"),
    },
    # Not a post counter, but a header line ("500 followers") that reads like a
    # relative time unless it is recognised as a count.
    "followers": {
        "en": ("follower", "followers"),
        "nl": ("volger", "volgers"),
        "de": ("follower", "abonnenten"),
        "fr": ("abonné", "abonnés"),
        "es": ("seguidor", "seguidores"),
        "it": ("follower", "seguaci"),
        "pt": ("seguidor", "seguidores"),
    },
    "replies": {
        "en": ("reply", "replies"),
        "nl": ("antwoord", "antwoorden"),
        "de": ("antwort", "antworten"),
        "fr": ("réponse", "réponses"),
        "es": ("respuesta", "respuestas"),
        "it": ("risposta", "risposte"),
        "pt": ("resposta", "respostas"),
    },
}

# Words after "<name> and 122 ..." that make a reaction line a total of the
# named person plus the others. "Maria and 122 others" is 123 reactions.
_OTHERS = frozenset(
    {
        "others",
        "other",
        "anderen",
        "andere",
        "weitere",
        "weiteren",
        "autres",
        "otros",
        "otras",
        "altri",
        "altre",
        "outros",
        "outras",
    }
)

_COUNT_NUMBER = r"\d[\d.,   ]*[kKmM]?"
_COUNT_LINE = re.compile(rf"^(?P<n>{_COUNT_NUMBER})\s+(?P<label>[^\W\d_][\w ]*?)\.?$")


def parse_count(token: str) -> int | None:
    """An integer from a displayed count: ``1,234``, ``1.234``, ``1 234``, ``1.2K``."""
    text = token.strip().replace(" ", " ").replace(" ", " ")
    if not text:
        return None
    multiplier = 1
    if text[-1] in "kK":
        multiplier, text = 1_000, text[:-1].strip()
    elif text[-1] in "mM":
        multiplier, text = 1_000_000, text[:-1].strip()
    if not text or not text[0].isdigit():
        return None
    if multiplier == 1:
        # Thousands separators in every locale: 1,234 / 1.234 / 1 234.
        if re.fullmatch(r"\d{1,3}(?:[., ]\d{3})+", text):
            return int(re.sub(r"[.,\s]", "", text))
        return int(text) if text.isdigit() else None
    # "1.2K" and "1,2K" are a decimal before the suffix.
    decimal = text.replace(",", ".")
    try:
        return int(round(float(decimal) * multiplier))
    except ValueError:
        return None


def count_label(line: str) -> tuple[str, int] | None:
    """A labelled count line as ``(kind, number)``, or ``None``.

    ``kind`` is ``comments``, ``reposts``, ``impressions``, ``reactions`` or
    ``replies``. The label must be the whole remainder of the line, so a
    sentence that happens to start with a number is not read as a count.
    """
    match = _COUNT_LINE.match(line.strip())
    if match is None:
        return None
    number = parse_count(match.group("n"))
    if number is None:
        return None
    label = match.group("label").strip().lower()
    for kind, languages in _COUNT_LABELS.items():
        for stems in languages.values():
            if label in stems:
                return kind, number
    return None


def reaction_total(line: str) -> int | None:
    """The reaction total in a line such as ``123``, ``Maria and 122 others``.

    A bare number is the total. A line led by a name and ending in "<n> others"
    counts the named person too, so the total is ``n + 1``. Anything else is not
    a reaction line.
    """
    stripped = line.strip()
    bare = parse_count(stripped)
    if bare is not None and re.fullmatch(_COUNT_NUMBER, stripped):
        return bare
    words = stripped.split()
    if len(words) >= 3 and words[-1].lower().rstrip(".") in _OTHERS:
        number = parse_count(words[-2])
        if number is not None:
            return number + 1
    labelled = count_label(stripped)
    if labelled is not None and labelled[0] == "reactions":
        return labelled[1]
    return None


# --- Buttons -----------------------------------------------------------------

# Whole-line labels of the action row under a post or a comment. The row is
# stripped from the end of a comment so the last real line of its text is kept.
_ACTION_LABELS: dict[str, tuple[str, ...]] = {
    "en": ("like", "reply", "comment", "repost", "send", "share", "report"),
    "nl": ("vind ik leuk", "reageren", "beantwoorden", "delen", "verzenden", "repost"),
    "de": ("gefällt mir", "antworten", "kommentieren", "teilen", "senden"),
    "fr": ("j'aime", "répondre", "commenter", "partager", "envoyer"),
    "es": ("me gusta", "responder", "comentar", "compartir", "enviar"),
    "it": ("mi piace", "rispondi", "commenta", "condividi", "invia"),
    "pt": ("gostei", "responder", "comentar", "compartilhar", "enviar"),
}
_ACTION_SET = frozenset(label for labels in _ACTION_LABELS.values() for label in labels)


def is_action_label(line: str) -> bool:
    """Whether *line* is only a like/reply/share style button label."""
    return line.strip().lower() in _ACTION_SET


# The control that opens a comment sort menu shows the current mode, and the
# menu items are the modes. Text is the only signal on a control that has no
# stable attribute, so both directions are in the table.
SORT_RELEVANT_LABELS: tuple[str, ...] = (
    "Most relevant",
    "Meest relevant",
    "Relevanteste",
    "Plus pertinents",
    "Más relevantes",
    "Più rilevanti",
    "Mais relevantes",
)
SORT_RECENT_LABELS: tuple[str, ...] = (
    "Most recent",
    "Meest recent",
    "Neueste",
    "Plus récents",
    "Más recientes",
    "Più recenti",
    "Mais recentes",
)

#: Buttons that reveal further comments, matched on the whole visible text.
LOAD_MORE_COMMENTS_LABELS: tuple[str, ...] = (
    "Load more comments",
    "Meer reacties laden",
    "Weitere Kommentare laden",
    "Charger plus de commentaires",
    "Cargar más comentarios",
    "Carica altri commenti",
    "Carregar mais comentários",
)


def is_sort_label(line: str) -> bool:
    """Whether *line* is the comment sort control or one of its modes."""
    lowered = line.strip().lower()
    return any(
        lowered == label.lower()
        for label in (*SORT_RELEVANT_LABELS, *SORT_RECENT_LABELS)
    )
