import pytest

from app.catalog import facets


@pytest.mark.parametrize(
    "query, expected",
    [
        ("dry food for dogs", "DOGS"),
        ("Nassfutter für Hunde", "DOGS"),
        ("comida para perros", "DOGS"),
        ("wet food for cats", "CATS"),
        ("Trockenfutter für Katzen", "CATS"),
        ("comida húmeda para gatos", "CATS"),
        ("something for my pet", None),  # no species named
        ("food for cats and dogs", None),  # both -> no constraint
    ],
)
def test_detect_pet_type(query, expected):
    assert facets.detect_pet_type(query) == expected


@pytest.mark.parametrize(
    "query, expected",
    [
        ("dry food", "DRY"),
        ("Trockenfutter für Katzen", "DRY"),
        ("pienso seco", "DRY"),
        ("wet food", "WET"),
        ("Nassfutter", "WET"),
        ("comida húmeda", "WET"),
        ("food for my dog", None),  # form not stated
        ("dry and wet food", None),  # both -> no constraint
    ],
)
def test_detect_food_form(query, expected):
    assert facets.detect_food_form(query) == expected


@pytest.mark.parametrize(
    "name, summary, expected",
    [
        ("Purina ONE Huhn Trockenfutter", "", "DRY"),
        ("Whiskas in Gelee Nassfutter", "", "WET"),
        ("Royal Canin AirLift Mousse", "", "WET"),
        ("Chuckit Ultra Squeaker Ball", "toy", None),  # non-food
    ],
)
def test_classify_food_form(name, summary, expected):
    assert facets.classify_food_form(name, "", summary) == expected


def test_classify_food_form_ignores_description_only_cross_reference():
    # A wet product whose *summary* is clean must not be swayed; the classifier
    # never reads the description, so a "complement to dry food" note elsewhere
    # cannot flip it. Here summary carries the wet cue and no dry cue.
    assert facets.classify_food_form("Schesir Filet", "1kg", "Saftiges Filet in Gelee") == "WET"
