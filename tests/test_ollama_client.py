import json

import httpx
import pytest

from app.core.errors import LLMUnavailableError
from app.llm.client import OllamaClient


def make_client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="http://ollama.test")
    return OllamaClient("http://ollama.test", 5.0, client=http)


async def test_chat_returns_message_content():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hello"}})

    client = make_client(handler)
    result = await client.chat("gemma4:e4b", "sys", "user msg", temperature=0.7)
    assert result == "hello"
    assert captured["json"]["model"] == "gemma4:e4b"
    assert captured["json"]["stream"] is False
    assert captured["json"]["options"]["temperature"] == 0.7
    assert captured["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert "format" not in captured["json"]


async def test_chat_json_mode_sets_format():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": '{"on_topic": true}'}})

    client = make_client(handler)
    await client.chat("m", "s", "u", json_mode=True)
    assert captured["json"]["format"] == "json"


async def test_chat_connect_error_raises_llm_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = make_client(handler)
    with pytest.raises(LLMUnavailableError):
        await client.chat("m", "s", "u")


async def test_chat_http_error_status_raises_llm_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = make_client(handler)
    with pytest.raises(LLMUnavailableError):
        await client.chat("m", "s", "u")


async def test_is_reachable_true_and_false():
    client_up = make_client(lambda req: httpx.Response(200, json={"models": []}))
    assert await client_up.is_reachable() is True

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client_down = make_client(down)
    assert await client_down.is_reachable() is False
