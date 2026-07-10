from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.ui import router as ui_router
from app.catalog.ingest import load_catalog
from app.catalog.repository import CatalogRepository
from app.chat.judge import Judge
from app.chat.service import ChatService
from app.core.config import Settings
from app.core.errors import LLMUnavailableError, UnknownSiteError
from app.core.logging import RequestIdMiddleware, setup_logging
from app.core.tracing import setup_tracing
from app.llm.client import OllamaClient
from app.retrieval.bm25 import BM25Retriever


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        variants, _report = load_catalog(
            app_settings.catalog_path, app_settings.max_plausible_price
        )
        repository = CatalogRepository(variants)
        llm_client = OllamaClient(app_settings.ollama_base_url, app_settings.llm_timeout_seconds)
        app.state.settings = app_settings
        app.state.repository = repository
        app.state.llm_client = llm_client
        app.state.chat_service = ChatService(
            judge=Judge(llm_client, app_settings.judge_model),
            retriever=BM25Retriever(repository),
            llm=llm_client,
            repository=repository,
            settings=app_settings,
        )
        yield
        await llm_client.aclose()

    setup_logging()
    setup_tracing(app_settings)
    app = FastAPI(title="Assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(router)
    app.include_router(ui_router)

    @app.exception_handler(UnknownSiteError)
    async def unknown_site_handler(request: Request, exc: UnknownSiteError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(LLMUnavailableError)
    async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError):
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The language model backend is unavailable. Please try again later."
            },
        )

    return app


app = create_app()
