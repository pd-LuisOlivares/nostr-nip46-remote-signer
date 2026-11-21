import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    # La API solo acepta cabeceras Host locales (anti DNS rebinding): el cliente de pruebas se conecta como un cliente local.
    return TestClient(create_app(announce_code=False), base_url="http://127.0.0.1")


def test_health_returns_200(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_health_body_is_exactly_status_ok(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_health_content_type_is_json(client: TestClient) -> None:
    content_type = client.get("/health").headers["content-type"]
    assert content_type.split(";")[0].strip() == "application/json"


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get("/no-existe").status_code == 404


def test_health_rejects_non_get_methods(client: TestClient) -> None:
    assert client.post("/health").status_code == 405
