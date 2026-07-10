import httpx
import pytest

from app.chat.service import ChatResult
from app.core.errors import LLMUnavailableError, UnknownSiteError
from app.main import create_app
from app.retrieval.base import ScoredVariant
from tests.helpers import FakeLLM, make_variant


class StubChatService:
    """Configurable stand-in for ChatService at the app.state seam."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def handle(self, site_id, query):
        if self.error is not None:
            raise self.error
        return self.result


class StubRepository:
    def site_ids(self):
        return [1, 3, 15]


def client_for(service):
    app = create_app()
    app.state.chat_service = service
    app.state.repository = StubRepository()
    app.state.llm_client = FakeLLM()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_chat_success_contract():
    scored = ScoredVariant(
        variant=make_variant(product_id=42, in_stock=False, rating_average=None,
                             rating_count=0, discount_label="-20%"),
        score=1.5,
    )
    service = StubChatService(result=ChatResult(answer="try this", products=[scored]))
    async with client_for(service) as client:
        response = await client.post("/chat", json={"site_id": 1, "query": "dog toy"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "try this"
    wrapper = body["retrieved_products"]
    assert wrapper["count"] == 1
    card = wrapper["products"][0]
    assert card["product_id"] == 42
    assert card["in_stock"] is False
    assert card["rating_average"] is None
    assert card["rating_count"] == 0
    assert card["discount_label"] == "-20%"


async def test_product_card_never_leaks_internal_fields():
    scored = ScoredVariant(variant=make_variant(), score=1.0)
    service = StubChatService(result=ChatResult(answer="ok", products=[scored]))
    async with client_for(service) as client:
        response = await client.post("/chat", json={"site_id": 1, "query": "dog toy"})
    card = response.json()["retrieved_products"]["products"][0]
    for internal in ("margin_pct", "monthly_sales_units", "revenue_last_30d", "stock_units"):
        assert internal not in card


async def test_chat_empty_products_shape():
    service = StubChatService(result=ChatResult(answer="sorry, no", products=[]))
    async with client_for(service) as client:
        response = await client.post("/chat", json={"site_id": 1, "query": "weather"})
    assert response.status_code == 200
    assert response.json()["retrieved_products"] == {"products": [], "count": 0}


async def test_unknown_site_maps_to_404_naming_valid_sites():
    service = StubChatService(error=UnknownSiteError(7, [1, 3, 15]))
    async with client_for(service) as client:
        response = await client.post("/chat", json={"site_id": 7, "query": "dog food"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "7" in detail and "[1, 3, 15]" in detail


async def test_llm_unavailable_maps_to_503():
    service = StubChatService(error=LLMUnavailableError("down"))
    async with client_for(service) as client:
        response = await client.post("/chat", json={"site_id": 1, "query": "dog food"})
    assert response.status_code == 503


@pytest.mark.parametrize("payload", [
    {"site_id": 1},                                  # missing query
    {"query": "hi"},                                 # missing site_id
    {"site_id": 1, "query": "   "},                  # blank query
    {"site_id": 1, "query": "x" * 2001},             # too long
    {"site_id": "one", "query": "hi"},               # wrong type
    {"site_id": 1, "query": "hi", "extra": True},    # extra field
])
async def test_validation_422(payload):
    async with client_for(StubChatService()) as client:
        response = await client.post("/chat", json=payload)
    assert response.status_code == 422


async def test_health():
    async with client_for(StubChatService()) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["catalog_loaded"] is True
    assert body["sites"] == [1, 3, 15]
    assert body["ollama"] in {"reachable", "unreachable"}


async def test_request_id_header_present():
    async with client_for(StubChatService()) as client:
        response = await client.get("/health")
    assert response.headers.get("X-Request-ID")
