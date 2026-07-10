"""Static web UI for manual testing and demos — a pure client of the API."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

_STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter()


@router.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")
