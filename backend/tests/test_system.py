from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    r = client.get("/api/v1/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_ready(client: TestClient) -> None:
    r = client.get("/api/v1/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_info(client: TestClient) -> None:
    r = client.get("/api/v1/info")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "libreta"
    assert body["content_dir_exists"] is True
