from app.llm.prompts import (
    DECLINES,
    LANGUAGE_NAMES,
    NO_MATCH_ANSWERS,
    generation_system,
    generation_user_prompt,
    judge_user_prompt,
    render_product_context,
)
from app.retrieval.base import ScoredVariant
from tests.helpers import make_variant


def _scored(**overrides):
    return ScoredVariant(variant=make_variant(**overrides), score=1.0)


def test_generation_system_names_the_site_language():
    assert "German" in generation_system("de-DE")
    assert "English" in generation_system("en-GB")
    assert "Spanish" in generation_system("es-ES")


def test_localized_answer_maps_cover_all_sites():
    for mapping in (DECLINES, NO_MATCH_ANSWERS):
        assert set(mapping) == set(LANGUAGE_NAMES) == {"de-DE", "en-GB", "es-ES"}
        assert all(mapping.values())


def test_context_contains_key_fields():
    context = render_product_context(
        [_scored(product_name="Wonder Ball", price=12.5, currency="GBP", discount_label="-20%")],
        max_chars=600,
    )
    assert "Wonder Ball" in context
    assert "12.50 GBP" in context
    assert "-20%" in context
    assert "In stock" in context


def test_out_of_stock_is_flagged():
    context = render_product_context([_scored(in_stock=False)], max_chars=600)
    assert "OUT OF STOCK" in context


def test_unrated_variant_shows_no_ratings_not_zero():
    context = render_product_context([_scored(rating_average=None, rating_count=0)], max_chars=600)
    assert "No ratings yet" in context
    assert "0.0" not in context


def test_details_truncated_to_budget():
    context = render_product_context([_scored(summary="", description="x" * 1000)], max_chars=100)
    details_line = next(line for line in context.splitlines() if line.startswith("Details:"))
    assert len(details_line) < 120
    assert details_line.endswith("…")


def test_ingredients_and_feeding_only_when_present():
    without = render_product_context([_scored()], max_chars=600)
    assert "Ingredients:" not in without
    with_food = render_product_context(
        [_scored(ingredients="chicken, rice", feeding_recommendations="50g daily")],
        max_chars=600,
    )
    assert "Ingredients: chicken, rice" in with_food
    assert "Feeding: 50g daily" in with_food


def test_multiple_variants_are_numbered():
    context = render_product_context([_scored(), _scored(variant_id="2.0")], max_chars=600)
    assert "Product 1:" in context and "Product 2:" in context


def test_user_prompts_embed_query():
    assert "muddy paws" in judge_user_prompt("muddy paws")
    prompt = generation_user_prompt("best toy?", "CONTEXT")
    assert "best toy?" in prompt and "CONTEXT" in prompt
