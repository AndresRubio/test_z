from pydantic import BaseModel

from app.api.schemas import DoneEvent, ErrorEvent, RetrievedEvent, TokenEvent

EVENT_NAMES: dict[type, str] = {
    RetrievedEvent: "retrieved",
    TokenEvent: "token",
    DoneEvent: "done",
    ErrorEvent: "error",
}


def sse_frame(event: BaseModel) -> str:
    """The only place SSE frame text is assembled. Accepts only the four
    registered event models — every byte on the wire went through Pydantic."""
    name = EVENT_NAMES[type(event)]
    return f"event: {name}\ndata: {event.model_dump_json()}\n\n"
