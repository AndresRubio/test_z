import logging

import pytest

from app.catalog.ingest import load_catalog
from app.catalog.repository import CatalogRepository
from app.core.errors import UnknownSiteError
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.hybrid import HybridRetriever
from tests.conftest import DATASET_PATH
from tests.helpers import FakeEmbedder, make_variant

KIDNEY_AXES = (("kidney", "renal"),)


def _clinical_corpus():
    """Six Variants: one lexical+semantic hit, one semantic-only paraphrase
    ("renal" ~ "kidney"), one lexical-only ("diet"), three fillers that keep
    BM25 IDF positive for the shared query terms."""
    kidney = make_variant(
        variant_id="a.1", product_name="Kidney Diet Complete",
        summary="clinical nutrition", description="",
    )
    renal = make_variant(
        variant_id="b.1", product_name="Renal Support",
        summary="clinical nutrition", description="",
    )
    snacks = make_variant(
        variant_id="c.1", product_name="Diet Snacks", summary="light snack", description="",
    )
    fillers = [
        make_variant(variant_id="f1.1", product_name="Nylon Leash", summary="", description=""),
        make_variant(variant_id="f2.1", product_name="Squeaky Ball", summary="", description=""),
        make_variant(variant_id="f3.1", product_name="Clumping Litter", summary="", description=""),
    ]
    return kidney, renal, snacks, fillers


def _hybrid(variants, axes, **knobs):
    embedder = FakeEmbedder(axes=axes)
    return HybridRetriever(CatalogRepository(variants), embedder, **knobs), embedder


async def test_fusion_ranks_dual_leg_hit_first():
    # kidney: top of BOTH legs; snacks: lexical only; renal: semantic only.
    # RRF must put the dual-leg hit first while keeping both single-leg hits.
    kidney, renal, snacks, fillers = _clinical_corpus()
    retriever, _ = _hybrid([kidney, renal, snacks, *fillers], KIDNEY_AXES)
    results = await retriever.retrieve(1, "kidney diet", k=5)
    ids = [r.variant.variant_id for r in results]
    assert ids[0] == "a.1"
    assert "b.1" in ids and "c.1" in ids


async def test_semantic_leg_recovers_paraphrase_bm25_misses():
    # "Renal Support" shares no token with the query; only the embedding leg
    # (kidney ~ renal on the same axis) can surface it. This is the shape of
    # the cross-lingual known_limitation the hybrid backend exists to fix.
    kidney, renal, snacks, fillers = _clinical_corpus()
    variants = [kidney, renal, snacks, *fillers]
    retriever, _ = _hybrid(variants, KIDNEY_AXES)
    lexical_only = BM25Retriever(CatalogRepository(variants))

    bm25_ids = [r.variant.variant_id for r in await lexical_only.retrieve(1, "kidney problems", 5)]
    hybrid_ids = [r.variant.variant_id for r in await retriever.retrieve(1, "kidney problems", 5)]
    assert "b.1" not in bm25_ids  # BM25 is blind to the paraphrase...
    assert "b.1" in hybrid_ids  # ...the semantic leg recovers it


async def test_pet_type_hard_filter_is_absolute_on_both_legs():
    # The cat Variant is the strongest match on BOTH legs for "chicken", yet a
    # dogs query must never surface it: pet_type is authoritative data.
    cat_food = make_variant(
        variant_id="c.1", product_name="Chicken Feast", pet_type="CATS",
        summary="tender chicken", description="chicken chunks",
    )
    dog_food = make_variant(
        variant_id="d.1", product_name="Chicken Dinner", pet_type="DOGS",
        summary="with chicken", description="",
    )
    fillers = [
        make_variant(variant_id="f1.1", product_name="Nylon Leash", summary="", description=""),
        make_variant(variant_id="f2.1", product_name="Squeaky Ball", summary="", description=""),
    ]
    retriever, _ = _hybrid([cat_food, dog_food, *fillers], (("chicken",),))
    results = await retriever.retrieve(1, "chicken for dogs", k=5)
    assert results, "expected some dog matches"
    assert all(r.variant.pet_type == "DOGS" for r in results)
    assert "c.1" not in [r.variant.variant_id for r in results]


async def test_food_form_soft_boost_survives_fusion():
    # Mirror of the BM25 food-form test: identical text, opposite forms. The
    # WET one must float up on a wet query and the DRY one must stay retrievable
    # (soft boost, not a filter) — on both legs and through the fusion.
    dry = make_variant(
        variant_id="d.1", product_name="Meadow Meal", summary="complete food for cats",
        description="", pet_type="CATS", food_form="DRY",
    )
    wet = make_variant(
        variant_id="w.1", product_name="Meadow Meal", summary="complete food for cats",
        description="", pet_type="CATS", food_form="WET",
    )
    fillers = [
        make_variant(variant_id="f1.1", product_name="Cat Bed", summary="plush",
                     description="", pet_type="CATS"),
        make_variant(variant_id="f2.1", product_name="Litter Box", summary="clay",
                     description="", pet_type="CATS"),
        make_variant(variant_id="f3.1", product_name="Scratch Post", summary="sisal",
                     description="", pet_type="CATS"),
    ]
    # dry first in the catalog: without the boost a stable tie would keep it on top
    retriever, _ = _hybrid([dry, wet, *fillers], (("food",),))
    results = await retriever.retrieve(1, "wet food for cats", k=5)
    forms = [r.variant.food_form for r in results]
    assert forms[0] == "WET"
    assert "DRY" in forms


async def test_query_embedding_lru_cache_hits():
    kidney, renal, snacks, fillers = _clinical_corpus()
    retriever, embedder = _hybrid([kidney, renal, snacks, *fillers], KIDNEY_AXES)
    precompute_calls = len(embedder.calls)  # one batched encode per Site
    await retriever.retrieve(1, "kidney diet", k=5)
    assert len(embedder.calls) == precompute_calls + 1
    await retriever.retrieve(1, "kidney diet", k=5)  # cache hit: no new encode
    assert len(embedder.calls) == precompute_calls + 1
    await retriever.retrieve(1, "renal snacks", k=5)  # different query: miss
    assert len(embedder.calls) == precompute_calls + 2


async def test_min_similarity_is_the_semantic_relevance_cutoff():
    # "Renal Care" shares no token with "kidney snack" and its cosine to the
    # query is ~0.707 (one of two query axes). Below the floor it must vanish
    # from the semantic leg — the analog of BM25 dropping score <= 0 docs.
    axes = (("kidney", "renal"), ("snack", "treat"))
    renal = make_variant(
        variant_id="b.1", product_name="Renal Care", summary="", description="",
    )
    filler = make_variant(
        variant_id="f1.1", product_name="Nylon Leash", summary="", description="",
    )
    permissive, _ = _hybrid([renal, filler], axes)  # default floor 0.25
    strict, _ = _hybrid([renal, filler], axes, min_similarity=0.9)
    assert "b.1" in [r.variant.variant_id for r in await permissive.retrieve(1, "kidney snack", 5)]
    assert "b.1" not in [r.variant.variant_id for r in await strict.retrieve(1, "kidney snack", 5)]


async def test_unknown_site_raises():
    retriever, _ = _hybrid([make_variant()], KIDNEY_AXES)
    with pytest.raises(UnknownSiteError):
        await retriever.retrieve(99, "dog food", k=5)


async def test_empty_query_returns_empty():
    retriever, _ = _hybrid([make_variant()], KIDNEY_AXES)
    assert await retriever.retrieve(1, "!!! ???", k=5) == []


async def test_precompute_logs_timing(caplog):
    kidney, renal, snacks, fillers = _clinical_corpus()
    with caplog.at_level(logging.INFO, logger="app.retrieval.hybrid"):
        _hybrid([kidney, renal, snacks, *fillers], KIDNEY_AXES)
    records = [r for r in caplog.records if r.message == "variant embeddings precomputed"]
    assert len(records) == 1
    assert records[0].variant_count == 6
    assert records[0].duration_ms >= 0


async def test_uninformative_embedder_degrades_to_pure_bm25_on_real_dataset():
    # A zero-signal embedder empties the semantic leg, so the hybrid ranking
    # must collapse to exactly the BM25 ordering — fusion never distorts the
    # lexical result when there is nothing to fuse.
    variants, _ = load_catalog(DATASET_PATH)
    repository = CatalogRepository(variants)
    hybrid = HybridRetriever(repository, FakeEmbedder(axes=()))
    bm25 = BM25Retriever(repository)
    query = "best dry food for a puppy with a sensitive stomach"
    hybrid_ids = [r.variant.variant_id for r in await hybrid.retrieve(3, query, 5)]
    bm25_ids = [r.variant.variant_id for r in await bm25.retrieve(3, query, 5)]
    assert hybrid_ids == bm25_ids
    assert 1383193 in [r.variant.product_id for r in await hybrid.retrieve(3, query, 5)]
