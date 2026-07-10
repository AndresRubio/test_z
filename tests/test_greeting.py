import pytest

from app.chat.greeting import is_greeting


@pytest.mark.parametrize(
    "query",
    [
        "hi",
        "Hi",
        "HELLO",
        "Hello!",
        "hey",
        "hey there",
        "hi there",
        "good morning",
        "Good Evening",
        "howdy",
        "hola",
        "¡Hola!",
        "buenas",
        "buenos días",
        "buenas tardes",
        "hallo",
        "Guten Tag",
        "moin",
        "grüß gott",
        "  hi  ",
        "hello :)",
        "hiii",
    ],
)
def test_recognises_bare_greetings(query):
    assert is_greeting(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "hi, do you have dog food?",
        "hello can you recommend a cat toy",
        "hola, busco comida para gato",
        "good food for my puppy",  # starts with 'good' but is a real query
        "what's the weather today?",
        "dog food",
        "",
        "highlighter for my desk",  # 'hi' must not match as a prefix
        "hey what's the best leash",
    ],
)
def test_ignores_greetings_bundled_with_real_queries(query):
    assert is_greeting(query) is False
