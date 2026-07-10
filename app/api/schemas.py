from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.retrieval.base import ScoredVariant

# Upper bound on resent turns: enough for a short shopping conversation, small
# enough that the Generator's context stays dominated by the product cards.
MAX_HISTORY_TURNS = 10


class ChatTurn(BaseModel):
    """One prior turn of the conversation, resent verbatim by the client."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: int
    query: str = Field(min_length=1, max_length=2000)
    stream: bool = False
    # Stateless multi-turn (design doc § Multi-turn, option a): the client
    # resends the transcript on every request and the server stays memoryless.
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)

    # TO_EXPLAIN — multi-turn is now stateless-by-contract: `history` above
    # carries prior turns to the Generator, but the server still keeps no
    # transcript and trusts whatever the client resends. The remaining option:
    # (b) stateful — a `conversation_id` keys a short server-side transcript
    # (smaller requests, server owns the truth; costs a store, TTL/eviction).
    # Either way a query-rewriting step must make the turn self-contained
    # before the Judge and Retriever, which still see one standalone query.
    # See docs/specs/conversation/
    # 2026-07-11-conversational-improvements-design.md § Multi-turn & follow-ups.

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class ProductCard(BaseModel):
    """Customer-safe representation of a retrieved Variant. Internal Fields
    cannot appear here: the model has no such fields."""

    product_id: int
    article_id: int
    variant_id: str
    product_name: str
    variant_name: str
    brand: str
    pet_type: str
    price: float
    currency: str
    discount_label: str | None
    rating_average: float | None
    rating_count: int
    in_stock: bool

    @classmethod
    def from_scored(cls, scored: ScoredVariant) -> "ProductCard":
        v = scored.variant
        return cls(
            product_id=v.product_id,
            article_id=v.article_id,
            variant_id=v.variant_id,
            product_name=v.product_name,
            variant_name=v.variant_name,
            brand=v.brand,
            pet_type=v.pet_type,
            price=v.price,
            currency=v.currency,
            discount_label=v.discount_label,
            rating_average=v.rating_average,
            rating_count=v.rating_count,
            in_stock=v.in_stock,
        )


class RetrievedProducts(BaseModel):
    products: list[ProductCard]
    count: int


class ChatResponse(BaseModel):
    answer: str
    retrieved_products: RetrievedProducts


class RetrievedEvent(BaseModel):
    """SSE `retrieved`: sent once, the moment retrieval completes."""

    retrieved_products: RetrievedProducts


class TokenEvent(BaseModel):
    """SSE `token`: one incremental answer delta."""

    delta: str


class DoneEvent(BaseModel):
    """SSE `done`: terminal on success; carries the full accumulated answer."""

    answer: str


class ErrorEvent(BaseModel):
    """SSE `error`: terminal on mid-stream failure (HTTP 200 is already sent)."""

    detail: str


class HealthResponse(BaseModel):
    status: str
    catalog_loaded: bool
    sites: list[int]
    ollama: str
