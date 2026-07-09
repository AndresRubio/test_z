from dataclasses import dataclass
from typing import Protocol

from app.catalog.models import Variant


@dataclass
class ScoredVariant:
    variant: Variant
    score: float


class Retriever(Protocol):
    """The retrieval seam (ADR 0001): BM25 in the PoC; multilingual vector
    search, hybrid fusion, and rerankers slot in behind this interface."""

    async def retrieve(self, site_id: int, query: str, k: int) -> list[ScoredVariant]:
        """Return up to k Variants for the Site, best first. Site is a hard filter."""
        ...
