import logging
import re

from rank_bm25 import BM25Okapi

from app.catalog import facets
from app.catalog.models import Variant
from app.catalog.repository import CatalogRepository
from app.core.errors import UnknownSiteError
from app.retrieval.base import ScoredVariant

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+")
_NAME_BOOST = 3  # name/brand tokens repeated so title hits outrank description hits
_FORM_MATCH = 1.5  # soft: lift the requested food form...
_FORM_MISS = 0.85  # ...and gently damp the opposite form. Deliberately mild: a
# strong semantic match (e.g. the only kidney-care diet, which is dry) must still
# win a "wet food" query on merit — form breaks near-ties, it does not exclude.


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def adjust_for_food_form(score: float, variant: Variant, form: str | None) -> float:
    """Soft food-form re-rank shared by every retrieval backend: lift the
    requested form (×1.5), gently damp the other (×0.85), never exclude."""
    if form is None or variant.food_form is None:
        return score
    return score * (_FORM_MATCH if variant.food_form == form else _FORM_MISS)


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
        matched = [(v, float(s)) for v, s in zip(self._variants[site_id], scores) if s > 0.0]
        kept = [(v, s) for v, s in matched if pet is None or v.pet_type == pet]
        if pet is not None or form is not None:
            # Supervision signal: which facets fired and what the hard pet
            # filter removed, so the retriever's shaping is auditable per query.
            logger.info(
                "retrieval facets applied",
                extra={
                    "site_id": site_id,
                    "pet_filter": pet,
                    "food_form_boost": form,
                    "lexical_matches": len(matched),
                    "after_pet_filter": len(kept),
                },
            )
        scored = [(v, adjust_for_food_form(s, v, form)) for v, s in kept]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [ScoredVariant(variant=v, score=s) for v, s in scored[:k]]
