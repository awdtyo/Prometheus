"""Route tests for investigation, catalog, and SSE endpoints."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.settings import Settings

CREATE_PAYLOAD = {
    "scenario_id": "scn_power_undervoltage",
    "title": "Power bus undervoltage",
    "description": "Battery heater fault telemetry.",
    "fault_type": "power_degradation",
    "metadata": {"requested_by": "test"},
}


def _create(client: TestClient, payload: dict[str, object] | None = None) -> dict[str, object]:
    response = client.post("/api/v1/investigations", json=payload or CREATE_PAYLOAD)
    assert response.status_code == 201
    return response.json()


def test_create_investigation(client: TestClient) -> None:
    body = _create(client)

    assert body["id"].startswith("inv_")
    assert body["investigation_id"] == body["id"]
    assert body["scenario_id"] == "scn_power_undervoltage"
    assert body["title"] == "Power bus undervoltage"
    assert body["status"] == "completed"
    assert body["progress"] == 100
    assert body["current_stage"] == "completed"
    assert body["created_at"].endswith("Z")
    assert body["completed_at"].endswith("Z")


def test_create_investigation_requires_scenario_id(client: TestClient) -> None:
    response = client.post("/api/v1/investigations", json={"title": "No scenario"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"]
    assert body["errors"][0]["loc"] == ["body", "scenario_id"]


def test_create_investigation_rejects_unknown_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/investigations",
        json={"scenario_id": "scn_001", "unexpected": True},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_investigation_rejects_blank_scenario_id(client: TestClient) -> None:
    response = client.post("/api/v1/investigations", json={"scenario_id": "   "})

    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"


def test_get_investigation(client: TestClient) -> None:
    created = _create(client)

    response = client.get(f"/api/v1/investigations/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_investigation_returns_problem(client: TestClient) -> None:
    response = client.get("/api/v1/investigations/inv_missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "not_found"
    assert body["resource"] == "Investigation"
    assert body["identifier"] == "inv_missing"


def test_list_investigations_and_paginate(client: TestClient) -> None:
    for index in range(3):
        _create(
            client,
            {
                "scenario_id": f"scn_{index}",
                "title": f"Investigation {index}",
            },
        )

    first_page = client.get("/api/v1/investigations", params={"limit": 2})
    assert first_page.status_code == 200
    body = first_page.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]

    second_page = client.get(
        "/api/v1/investigations",
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None

    first_ids = {item["id"] for item in body["items"]}
    second_ids = {item["id"] for item in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_list_investigations_rejects_bad_cursor(client: TestClient) -> None:
    response = client.get(
        "/api/v1/investigations",
        params={"cursor": "not-a-real-cursor"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_cursor"


def test_list_investigations_limit_validation(client: TestClient) -> None:
    response = client.get("/api/v1/investigations", params={"limit": 500})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_hypotheses_are_ranked(client: TestClient) -> None:
    created = _create(client)

    response = client.get(f"/api/v1/investigations/{created['id']}/hypotheses")

    assert response.status_code == 200
    body = response.json()
    assert body["investigation_id"] == created["id"]
    hypotheses = body["hypotheses"]
    assert len(hypotheses) == 3
    scores = [hypothesis["score"] for hypothesis in hypotheses]
    assert scores == sorted(scores, reverse=True)
    assert all(hypothesis["evidence_ids"] for hypothesis in hypotheses)


def test_hypotheses_unknown_investigation(client: TestClient) -> None:
    response = client.get("/api/v1/investigations/inv_missing/hypotheses")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_timeline_is_chronological(client: TestClient) -> None:
    created = _create(client)

    response = client.get(f"/api/v1/investigations/{created['id']}/timeline")

    assert response.status_code == 200
    body = response.json()
    assert body["investigation_id"] == created["id"]
    assert len(body["events"]) == 4
    timestamps = [event["timestamp"] for event in body["events"]]
    assert timestamps == sorted(timestamps)
    assert body["events"][-1]["severity"] == "critical"


def test_timeline_unknown_investigation(client: TestClient) -> None:
    response = client.get("/api/v1/investigations/inv_missing/timeline")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_scenarios(client: TestClient) -> None:
    response = client.get("/api/v1/scenarios")

    assert response.status_code == 200
    scenarios = response.json()["items"]
    assert len(scenarios) >= 1
    assert all({"id", "name", "description", "fault_types"} <= set(item) for item in scenarios)


def test_subsystems(client: TestClient) -> None:
    response = client.get("/api/v1/subsystems")

    assert response.status_code == 200
    subsystems = response.json()["items"]
    assert len(subsystems) >= 1
    assert all({"id", "name", "description", "depends_on"} <= set(item) for item in subsystems)


def test_sse_stream_emits_progress_and_completion(client: TestClient) -> None:
    created = _create(client)

    with client.stream("GET", f"/api/v1/investigations/{created['id']}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        payload = "".join(response.iter_text())

    events = [block for block in payload.strip().split("\n\n") if block]
    assert len(events) == 7
    assert "event: progress" in events[0]
    assert "event: complete" in events[-1]

    data_lines = [
        line.removeprefix("data: ")
        for block in events
        for line in block.splitlines()
        if line.startswith("data: ")
    ]
    parsed = [json.loads(line) for line in data_lines]
    assert parsed[0]["progress"] == 0
    assert parsed[-1]["progress"] == 100
    assert parsed[-1]["status"] == "completed"
    assert all(event["investigation_id"] == created["id"] for event in parsed)


def test_sse_unknown_investigation_returns_problem(client: TestClient) -> None:
    response = client.get("/api/v1/investigations/inv_missing/events")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "not_found"


def test_legacy_unversioned_investigation_alias(client: TestClient) -> None:
    response = client.post("/api/investigations", json={"scenario_id": "scn_001"})

    assert response.status_code == 201
    assert response.json()["scenario_id"] == "scn_001"


def test_service_initializes_without_running_lifespan(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "no_lifespan.db",
    )
    client = TestClient(create_app(settings))
    try:
        response = client.post("/api/v1/investigations", json={"scenario_id": "scn_001"})
    finally:
        client.close()

    assert response.status_code == 201
