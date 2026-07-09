import json
import logging

import httpx
from fastapi import FastAPI

from app.core.logging import JsonFormatter, RequestIdMiddleware, request_id_var


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _record(msg="hello", **extra):
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emits_json_with_request_id():
    token = request_id_var.set("req-123")
    try:
        entry = _format(_record())
    finally:
        request_id_var.reset(token)
    assert entry["message"] == "hello"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["request_id"] == "req-123"


def test_formatter_includes_stage_fields_when_present():
    entry = _format(_record("stage complete", stage="retrieve", duration_ms=12))
    assert entry["stage"] == "retrieve"
    assert entry["duration_ms"] == 12


def test_formatter_omits_stage_fields_when_absent():
    entry = _format(_record())
    assert "stage" not in entry and "duration_ms" not in entry


def _middleware_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    async def ping():
        return {"request_id": request_id_var.get()}

    return app


async def test_middleware_generates_request_id_and_echoes_header():
    transport = httpx.ASGITransport(app=_middleware_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ping")
    header_id = response.headers["X-Request-ID"]
    assert header_id
    assert response.json()["request_id"] == header_id


async def test_middleware_propagates_incoming_request_id(caplog):
    transport = httpx.ASGITransport(app=_middleware_app())
    with caplog.at_level(logging.INFO, logger="app.request"):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ping", headers={"X-Request-ID": "abc42"})
    assert response.headers["X-Request-ID"] == "abc42"
    access = [r for r in caplog.records if r.name == "app.request"]
    assert access and hasattr(access[0], "duration_ms")
