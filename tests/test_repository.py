import pytest

from app.catalog.repository import CatalogRepository
from app.core.errors import UnknownSiteError
from tests.helpers import make_variant


def test_partitions_by_site():
    repo = CatalogRepository(
        [
            make_variant(variant_id="1.0", site_id=1),
            make_variant(variant_id="2.0", site_id=3, locale="en-GB", currency="GBP"),
            make_variant(variant_id="3.0", site_id=3, locale="en-GB", currency="GBP"),
        ]
    )
    assert repo.site_ids() == [1, 3]
    assert len(repo.variants_for_site(3)) == 2
    assert all(v.site_id == 3 for v in repo.variants_for_site(3))


def test_site_metadata_derived_from_variants():
    repo = CatalogRepository([make_variant(site_id=15, locale="es-ES", currency="EUR")])
    site = repo.site_for(15)
    assert (site.site_id, site.locale, site.currency) == (15, "es-ES", "EUR")


def test_unknown_site_raises_with_valid_sites():
    repo = CatalogRepository([make_variant(site_id=1)])
    with pytest.raises(UnknownSiteError) as exc_info:
        repo.variants_for_site(99)
    assert exc_info.value.valid_sites == [1]
    with pytest.raises(UnknownSiteError):
        repo.site_for(99)


def test_variants_for_site_returns_copy():
    repo = CatalogRepository([make_variant(site_id=1)])
    repo.variants_for_site(1).clear()
    assert len(repo.variants_for_site(1)) == 1
