from fastapi import APIRouter, Request

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ProductCard,
    RetrievedProducts,
)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    service = request.app.state.chat_service
    result = await service.handle(payload.site_id, payload.query)
    cards = [ProductCard.from_scored(s) for s in result.products]
    return ChatResponse(
        answer=result.answer,
        retrieved_products=RetrievedProducts(products=cards, count=len(cards)),
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    repository = request.app.state.repository
    reachable = await request.app.state.llm_client.is_reachable()
    return HealthResponse(
        status="ok",
        catalog_loaded=True,
        sites=repository.site_ids(),
        ollama="reachable" if reachable else "unreachable",
    )
