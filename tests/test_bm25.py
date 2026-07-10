import pytest

from app.catalog.ingest import load_catalog
from app.catalog.repository import CatalogRepository
from app.core.errors import UnknownSiteError
from app.retrieval.bm25 import BM25Retriever, tokenize
from tests.conftest import DATASET_PATH
from tests.helpers import make_variant


@pytest.fixture(scope="module")
def real_retriever():
    variants, _ = load_catalog(DATASET_PATH)
    return BM25Retriever(CatalogRepository(variants))


def test_tokenize_is_lowercase_unicode():
    assert tokenize("Größe L: Ø 7,6 cm — Ball!") == ["größe", "l", "ø", "7", "6", "cm", "ball"]


async def test_known_query_finds_expected_variant(real_retriever):
    results = await real_retriever.retrieve(
        3, "best dry food for a puppy with a sensitive stomach", k=5
    )
    ids = [r.variant.product_id for r in results]
    assert 1383193 in ids  # Eukanuba Special Care Puppy Sensitive Digestion


async def test_site_isolation(real_retriever):
    results = await real_retriever.retrieve(3, "Chuckit Ultra Squeaker Ball", k=10)
    assert all(r.variant.site_id == 3 for r in results)
    assert 759837 not in [r.variant.product_id for r in results]  # site-1-only Product


async def test_no_match_returns_empty(real_retriever):
    assert await real_retriever.retrieve(3, "xyzzblorp qwertyplex", k=5) == []


async def test_empty_query_returns_empty(real_retriever):
    assert await real_retriever.retrieve(3, "!!! ???", k=5) == []


async def test_unknown_site_raises(real_retriever):
    with pytest.raises(UnknownSiteError):
        await real_retriever.retrieve(99, "dog food", k=5)


async def test_quarantined_variants_never_retrievable(real_retriever):
    # All 24 quarantined Variants are priced >= 500; nothing retrievable may be.
    for site_id in (1, 3, 15):
        results = await real_retriever.retrieve(site_id, "Natural Trainer food pack", k=20)
        assert all(r.variant.price < 500.0 for r in results)


async def test_pet_type_query_hard_filters_other_pet(real_retriever):
    # "Nassfutter für Hunde" = wet food for DOGS; today the top hits are CATS
    # (Whiskas, Felix) because BM25 only tokenizes pet_type. It is authoritative
    # data, so a dog query must never surface a cat Variant.
    results = await real_retriever.retrieve(1, "Nassfutter für Hunde", k=5)
    assert results, "expected some dog matches"
    assert all(r.variant.pet_type == "DOGS" for r in results)


async def test_food_form_intent_boosts_matching_form():
    # Two cat foods with identical searchable text (so BM25 scores them equally)
    # differing only in food_form. A "wet" query must float the WET one up; the
    # DRY one is boosted, not excluded, so it still appears.
    wet = make_variant(
        variant_id="w.1", product_name="Meadow Meal", summary="complete food for cats",
        pet_type="CATS", food_form="WET",
    )
    dry = make_variant(
        variant_id="d.1", product_name="Meadow Meal", summary="complete food for cats",
        pet_type="CATS", food_form="DRY",
    )
    fillers = [
        make_variant(variant_id="f1.1", product_name="Dog Leash", summary="nylon", pet_type="CATS"),
        make_variant(variant_id="f2.1", product_name="Cat Bed", summary="plush", pet_type="CATS"),
        make_variant(variant_id="f3.1", product_name="Litter Box", summary="clay", pet_type="CATS"),
    ]
    retriever = BM25Retriever(CatalogRepository([dry, wet, *fillers]))
    results = await retriever.retrieve(1, "wet food for cats", k=5)
    forms = [r.variant.food_form for r in results]
    assert forms[0] == "WET"
    assert "DRY" in forms  # boosted, not filtered out


async def test_strong_semantic_match_survives_opposite_form_query(real_retriever):
    # "wet food for a cat with kidney problems" — the best clinical match is
    # Hill's k/d, which is a DRY diet. The soft form penalty must not bury it:
    # form breaks near-ties, it never overrides a strong relevance signal.
    results = await real_retriever.retrieve(3, "wet food for a cat with kidney problems", k=5)
    assert 2567570 in [r.variant.product_id for r in results]


async def test_name_match_outranks_description_match():
    in_name = make_variant(
        variant_id="a.1", product_name="SuperBall Deluxe", description="A toy for dogs."
    )
    in_desc = make_variant(
        variant_id="b.1",
        product_name="Chew Bone",
        description="Works a bit like a superball for dogs.",
    )
    # Filler Variants (no "superball") enlarge the corpus so the shared term's
    # BM25 IDF stays positive — on a 2-doc corpus a term in both docs has
    # negative IDF and both get dropped by the score > 0 filter.
    fillers = [
        make_variant(
            variant_id="c.1", product_name="Cat Litter", description="Clumping clay litter."
        ),
        make_variant(
            variant_id="d.1", product_name="Dog Leash", description="Durable nylon leash."
        ),
        make_variant(
            variant_id="e.1", product_name="Fish Flakes", description="Aquarium flake food."
        ),
    ]
    retriever = BM25Retriever(CatalogRepository([in_name, in_desc, *fillers]))
    results = await retriever.retrieve(1, "superball", k=2)
    assert results[0].variant.product_name == "SuperBall Deluxe"
