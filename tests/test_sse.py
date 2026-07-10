import json

import pytest
from pydantic import BaseModel

from app.api.schemas import (
    DoneEvent,
    ErrorEvent,
    ProductCard,
    RetrievedEvent,
    RetrievedProducts,
    TokenEvent,
)
from app.api.sse import EVENT_NAMES, sse_frame
from app.retrieval.base import ScoredVariant
from tests.helpers import make_variant


def _retrieved_event():
    card = ProductCard.from_scored(ScoredVariant(variant=make_variant(), score=1.0))
    return RetrievedEvent(retrieved_products=RetrievedProducts(products=[card], count=1))


def test_every_event_type_has_a_wire_name():
    assert EVENT_NAMES == {
        RetrievedEvent: "retrieved",
        TokenEvent: "token",
        DoneEvent: "done",
        ErrorEvent: "error",
    }


@pytest.mark.parametrize(
    ("event", "name"),
    [
        (TokenEvent(delta="Hel"), "token"),
        (DoneEvent(answer="Hello"), "done"),
        (ErrorEvent(detail="the model became unavailable"), "error"),
    ],
)
def test_sse_frame_format(event, name):
    frame = sse_frame(event)
    assert frame == f"event: {name}\ndata: {event.model_dump_json()}\n\n"


def test_sse_frame_data_is_single_line_json():
    frame = sse_frame(_retrieved_event())
    lines = frame.rstrip("\n").split("\n")
    assert lines[0] == "event: retrieved"
    assert lines[1].startswith("data: ")
    payload = json.loads(lines[1][len("data: ") :])
    assert payload["retrieved_products"]["count"] == 1
    assert payload["retrieved_products"]["products"][0]["product_name"] == "Test Product"


def test_sse_frame_rejects_unregistered_models():
    class NotAnEvent(BaseModel):
        x: int

    with pytest.raises(KeyError):
        sse_frame(NotAnEvent(x=1))
