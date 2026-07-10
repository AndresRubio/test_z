from collections.abc import AsyncIterator
from contextlib import aclosing

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ProductCard,
    RetrievedProducts,
)
from app.api.sse import sse_frame

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request):
    service = request.app.state.chat_service

    if payload.stream:
        # Streaming trades whole-response validation for latency: FastAPI cannot
        # apply `response_model` to a StreamingResponse, so validation is per-event
        # (every frame is a Pydantic model from api/schemas.py, never a hand-built
        # dict). If per-frame guarantees ever aren't enough, the alternatives are:
        # buffer the complete answer and validate it before sending — which gives
        # back the ~30s perceived latency this endpoint exists to hide — or make
        # non-streaming fast enough to not need SSE via a faster inference server,
        # which trades hosted-GPU cost against free local Ollama.
        events = service.handle_stream(payload.site_id, payload.query, payload.history)
        # Pull the first event before committing the response so pre-stream
        # failures (unknown site, judge-stage LLM down) still map to 404/503.
        first = await anext(events)

        async def frames() -> AsyncIterator[str]:
            async with aclosing(events):
                yield sse_frame(first)
                async for event in events:
                    yield sse_frame(event)

        return StreamingResponse(frames(), media_type="text/event-stream")

    result = await service.handle(payload.site_id, payload.query, payload.history)
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
