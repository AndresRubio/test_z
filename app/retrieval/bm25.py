import re

from rank_bm25 import BM25Okapi

from app.catalog import facets
from app.catalog.models import Variant
from app.catalog.repository import CatalogRepository
from app.core.errors import UnknownSiteError
from app.retrieval.base import ScoredVariant

_TOKEN_RE = re.compile(r"\w+")
_NAME_BOOST = 3  # name/brand tokens repeated so title hits outrank description hits
_FORM_MATCH = 1.5  # soft: lift the requested food form...
_FORM_MISS = 0.6  # ...and damp the opposite form, without excluding it


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _document_tokens(variant: Variant) -> list[str]:
    boosted = tokenize(f"{variant.product_name} {variant.brand}") * _NAME_BOOST
    rest = tokenize(
        " ".join(
            [
                variant.variant_name,
                variant.pet_type,
                variant.summary,
                variant.description,
                variant.ingredients,
                variant.feeding_recommendations,
            ]
        )
    )
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
        pet = facets.detect_pet_type(query)  # authoritative -> hard filter
        form = facets.detect_food_form(query)  # text-derived -> soft re-rank
        scored = [
            (v, self._adjust(float(s), v, form))
            for v, s in zip(self._variants[site_id], scores)
            if s > 0.0 and (pet is None or v.pet_type == pet)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [ScoredVariant(variant=v, score=s) for v, s in scored[:k]]

    @staticmethod
    def _adjust(score: float, variant: Variant, form: str | None) -> float:
        if form is None or variant.food_form is None:
            return score
        return score * (_FORM_MATCH if variant.food_form == form else _FORM_MISS)
