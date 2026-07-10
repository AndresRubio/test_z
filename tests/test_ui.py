import httpx

from app.main import create_app


def client():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_index_serves_html():
    async with client() as c:
        response = await c.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


async def test_index_not_in_openapi_schema():
    async with client() as c:
        response = await c.get("/openapi.json")
    assert "/" not in response.json()["paths"]


async def test_index_declares_a_favicon():
    async with client() as c:
        response = await c.get("/")
    assert '<link rel="icon"' in response.text


async def test_index_page_wires_up_the_api():
    async with client() as c:
        response = await c.get("/")
    page = response.text
    assert 'id="site-select"' in page
    assert 'id="composer"' in page
    assert "/chat" in page
    assert "/health" in page


async def test_console_requests_streaming_and_parses_sse():
    async with client() as c:
        response = await c.get("/")
    assert "stream: true" in response.text  # JS object literal in the fetch body
    assert "text/event-stream" in response.text
