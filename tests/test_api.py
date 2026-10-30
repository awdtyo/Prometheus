"""Smoke tests for the HTTP surface."""

from fastapi.testclient import TestClient

from backend.version import get_core_version


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Mission Autopsy API",
        "version": get_core_version(),
        "environment": "test",
    }


def test_legacy_health_alias_still_works(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_includes_versioned_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/investigations" in paths
    assert "/api/v1/investigations/{investigation_id}" in paths
    assert "/api/v1/investigations/{investigation_id}/hypotheses" in paths
    assert "/api/v1/investigations/{investigation_id}/timeline" in paths
    assert "/api/v1/investigations/{investigation_id}/events" in paths
    assert "/api/v1/scenarios" in paths
    assert "/api/v1/scenarios/{scenario_id}" in paths
    assert "/api/v1/scenarios/{scenario_id}/inject" in paths
    assert "/api/v1/runs" in paths
    assert "/api/v1/subsystems" in paths


def test_root_redirects_to_docs(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_route_returns_problem_json(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 404
    assert body["code"] == "not_found"
    assert body["instance"] == "/api/v1/does-not-exist"


def test_method_not_allowed_returns_problem_json(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "method_not_allowed"


def test_request_id_header_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["x-request-id"] == "test-request-id"
