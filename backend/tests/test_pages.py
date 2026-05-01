from fastapi.testclient import TestClient


def test_get_tree(client: TestClient) -> None:
    r = client.get("/api/v1/pages/tree")
    assert r.status_code == 200
    nodes = r.json()
    paths = {n["path"] for n in nodes}
    assert "index" in paths
    assert "recipes" in paths
    recipes = next(n for n in nodes if n["path"] == "recipes")
    assert recipes["is_directory"] is True
    child_paths = {c["path"] for c in recipes["children"]}
    assert "recipes/pizza-dough" in child_paths


def test_get_page_index(client: TestClient) -> None:
    r = client.get("/api/v1/pages/index")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Home"
    assert "Welcome." in body["body"]


def test_get_page_nested(client: TestClient) -> None:
    r = client.get("/api/v1/pages/recipes/pizza-dough")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Pizza Dough"
    assert "food" in body["meta"]["tags"]


def test_get_page_not_found(client: TestClient) -> None:
    r = client.get("/api/v1/pages/does-not-exist")
    assert r.status_code == 404


def test_get_page_traversal_blocked(client: TestClient) -> None:
    r = client.get("/api/v1/pages/../etc/passwd")
    assert r.status_code in (400, 404)  # FastAPI may normalize before our handler sees it
