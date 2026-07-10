from starlette.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import DATASET_PATH


def test_app_boots_with_real_catalog():
    settings = Settings(_env_file=None, catalog_path=DATASET_PATH)
    app = create_app(settings)
    with TestClient(app) as client:  # runs lifespan; /health needs no Ollama
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["catalog_loaded"] is True
    assert body["sites"] == [1, 3, 15]
    # A local Ollama may or may not be running on the dev machine — either is fine.
    assert body["ollama"] in {"reachable", "unreachable"}
