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


async def test_index_page_wires_up_the_api():
    async with client() as c:
        response = await c.get("/")
    page = response.text
    assert 'id="site-select"' in page
    assert 'id="composer"' in page
    assert "/chat" in page
    assert "/health" in page
