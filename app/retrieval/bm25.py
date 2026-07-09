import re

from rank_bm25 import BM25Okapi

from app.catalog.models import Variant
from app.catalog.repository import CatalogRepository
from app.core.errors import UnknownSiteError
from app.retrieval.base import ScoredVariant

_TOKEN_RE = re.compile(r"\w+")
_NAME_BOOST = 3  # name/brand tokens repeated so title hits outrank description hits


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _document_tokens(variant: Variant) -> list[str]:
    boosted = tokenize(f"{variant.product_name} {variant.brand}") * _NAME_BOOST
    rest = tokenize(" ".join([
        variant.variant_name, variant.pet_type, variant.summary,
        variant.description, variant.ingredients, variant.feeding_recommendations,
    ]))
    return boosted + rest


class BM25Retriever:
    """Lexical retrieval over per-Site BM25 indexes built once at startup."""

    def __init__(self, repository: CatalogRepository):
        self._variants: dict[int, list[Variant]] = {}
        self._indexes: dict[int, BM25Okapi] = {}
        for site_id in repository.site_ids():
            variants = repository.variants_for_site(site_id)
            self._variants[site_id] = variants
            self._indexes[site_id] = BM25Okapi([_document_tokens(v) for v in variants])

    async def retrieve(self, site_id: int, query: str, k: int) -> list[ScoredVariant]:
        if site_id not in self._indexes:
            raise UnknownSiteError(site_id, sorted(self._indexes))
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self._indexes[site_id].get_scores(tokens)
        ranked = sorted(
            zip(self._variants[site_id], scores), key=lambda pair: pair[1], reverse=True
        )
        return [ScoredVariant(variant=v, score=float(s)) for v, s in ranked[:k] if s > 0.0]
