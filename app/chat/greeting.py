"""Pipeline pre-stage: recognise a bare greeting with zero LLM calls.

A message like "Hi" or "Hola" would otherwise spend a Judge call only to be
declined as chit-chat. We short-circuit it to a static, welcoming reply in the
Site locale — the same zero-cost template pattern as DECLINES / NO_MATCH_ANSWERS.

Deliberately conservative: we match the *whole* normalised message, never a
prefix, so a greeting bundled with a real question ("hi, do you have dog food?")
still reaches the full Judge -> Retriever -> Generator pipeline.
"""

import re

# Accents folded so "buenos días" == "buenos dias" and "grüß" == "gruess";
# casefold() already lowercases and expands ß -> ss before this runs.
_FOLD = str.maketrans(
    {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n", "à": "a", "è": "e"}
)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)

# The three Site locales. A greeting we miss is not a bug: it simply takes the
# slower Judge path and still gets a correct reply, so we stay conservative and
# never list a word that doubles as a real product query.
_GREETINGS = frozenset(
    {
        # English
        "hi", "hii", "hiii", "hello", "helo", "hey", "heya", "hiya", "yo",
        "hi there", "hey there", "hello there", "howdy", "greetings",
        "good morning", "good afternoon", "good evening", "good day",
        # Spanish
        "hola", "holaa", "buenas", "buenos dias", "buenas tardes",
        "buenas noches", "buen dia", "que tal", "hola que tal", "saludos",
        # German
        "hallo", "hallo zusammen", "moin", "moin moin", "servus", "guten tag",
        "guten morgen", "guten abend", "gruss gott", "gruezi",
    }
)


def _normalise(query: str) -> str:
    text = query.casefold().translate(_FOLD)
    return " ".join(_NON_WORD.sub(" ", text).split())


def is_greeting(query: str) -> bool:
    """True only when the entire message is a recognised greeting."""
    return _normalise(query) in _GREETINGS
