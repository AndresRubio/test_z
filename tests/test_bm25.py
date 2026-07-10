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
