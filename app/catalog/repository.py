from collections import defaultdict

from app.catalog.models import Site, Variant
from app.core.errors import UnknownSiteError


class CatalogRepository:
    """In-memory catalog store, hard-partitioned by Site."""

    def __init__(self, variants: list[Variant]):
        by_site: dict[int, list[Variant]] = defaultdict(list)
        for variant in variants:
            by_site[variant.site_id].append(variant)
        self._by_site = dict(by_site)
        self._sites = {
            site_id: Site(
                site_id=site_id,
                locale=site_variants[0].locale,
                currency=site_variants[0].currency,
            )
            for site_id, site_variants in self._by_site.items()
        }

    def site_ids(self) -> list[int]:
        return sorted(self._by_site)

    def site_for(self, site_id: int) -> Site:
        if site_id not in self._sites:
            raise UnknownSiteError(site_id, self.site_ids())
        return self._sites[site_id]

    def variants_for_site(self, site_id: int) -> list[Variant]:
        if site_id not in self._by_site:
            raise UnknownSiteError(site_id, self.site_ids())
        return list(self._by_site[site_id])
