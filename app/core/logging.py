import json
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_EXTRA_KEYS = ("stage", "duration_ms", "site_id")


class JsonFormatter(logging.Formatter):
    """One JSON object per line; carries the request id and stage timing fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key in _EXTRA_KEYS:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logging.getLogger("app.request").info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={"duration_ms": round((time.perf_counter() - started) * 1000)},
            )
            return response
        finally:
            request_id_var.reset(token)
