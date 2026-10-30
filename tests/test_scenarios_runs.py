"""Scenario detail, fault injection, and queued run endpoint tests."""

from fastapi.testclient import TestClient

from backend.db import runs as run_repository

SCENARIO_ID = "scn_power_undervoltage"
FAULT_START = "2026-10-30T12:01:00Z"
FAULT_CONFIG = {
    "fault_type": "power_loss",
    "target_subsystem": "power",
    "start_time": FAULT_START,
    "duration_seconds": 120,
    "magnitude": 40,
}


def test_get_scenario_detail(client: TestClient) -> None:
    response = client.get(f"/api/v1/scenarios/{SCENARIO_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == SCENARIO_ID
    assert body["mission_start_utc"] == "2026-10-30T12:00:00.000Z"
    assert body["duration_seconds"] == 600
    assert body["subsystems"]
    assert body["telemetry_parameters"]
    assert body["fault_options"]
    assert {"power_loss", "power_degradation"} <= set(body["fault_types"])


def test_get_unknown_scenario_returns_problem(client: TestClient) -> None:
    response = client.get("/api/v1/scenarios/scn_missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "not_found"
    assert body["resource"] == "Scenario"
    assert body["identifier"] == "scn_missing"


def test_inject_fault_returns_preview_without_mutating_scenario(
    client: TestClient,
) -> None:
    before = client.get(f"/api/v1/scenarios/{SCENARIO_ID}").json()

    response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/inject",
        json=FAULT_CONFIG,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["injection_id"].startswith("inj_")
    assert body["scenario_id"] == SCENARIO_ID
    assert body["preview"] is True
    assert body["applied"] is False
    returned_fault = body["fault_config"]
    assert returned_fault["fault_type"] == "power_loss"
    assert returned_fault["target_subsystem"] == "power"
    assert returned_fault["duration_seconds"] == 120
    assert returned_fault["magnitude"] == 40
    assert returned_fault["start_time"] == "2026-10-30T12:01:00.000Z"
    assert body["effective_start_time"] == "2026-10-30T12:01:00.000Z"
    assert body["effective_end_time"] == "2026-10-30T12:03:00.000Z"

    after = client.get(f"/api/v1/scenarios/{SCENARIO_ID}").json()
    assert after == before
    assert body["scenario"] == before


def test_inject_unknown_scenario_returns_problem(client: TestClient) -> None:
    response = client.post(
        "/api/v1/scenarios/scn_missing/inject",
        json=FAULT_CONFIG,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_inject_rejects_unsupported_fault_type(client: TestClient) -> None:
    payload = {**FAULT_CONFIG, "fault_type": "unknown"}

    response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/inject",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_fault_type"


def test_inject_rejects_invalid_target(client: TestClient) -> None:
    payload = {**FAULT_CONFIG, "target_subsystem": "communications"}

    response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/inject",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_fault_target"


def test_inject_rejects_fault_outside_mission_window(client: TestClient) -> None:
    payload = {
        **FAULT_CONFIG,
        "start_time": "2026-10-30T11:59:00Z",
    }

    response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/inject",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "fault_outside_scenario"


def test_inject_rejects_out_of_range_duration(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/inject",
        json={**FAULT_CONFIG, "duration_seconds": 601},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_fault_duration"


def test_inject_rejects_out_of_range_magnitude(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/inject",
        json={**FAULT_CONFIG, "magnitude": 101},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_fault_magnitude"


def test_inject_rejects_invalid_fault_payload(client: TestClient) -> None:
    payload = {**FAULT_CONFIG, "duration_seconds": 0}

    response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/inject",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_run_queues_and_persists(client: TestClient) -> None:
    response = client.post(
        "/api/v1/runs",
        json={"scenario_id": SCENARIO_ID, "title": "Power investigation"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["run_id"].startswith("run_")
    assert body["scenario_id"] == SCENARIO_ID
    assert body["status"] == "queued"
    assert body["title"] == "Power investigation"
    assert body["queue_position"] == 1
    assert body["message"] == "Investigation queued."
    assert body["created_at"].endswith("Z")
    assert body["queued_at"].endswith("Z")

    assert body["investigation_config"]["fault_config"]["fault_type"] == "power_loss"
    assert body["fault_config"]["target_subsystem"] == "power"

    settings = client.app.state.settings
    record = run_repository.get_run(settings.database_path, body["run_id"])
    assert record is not None
    assert record.status == "queued"
    assert record.scenario_id == SCENARIO_ID


def test_create_run_reports_queue_position(client: TestClient) -> None:
    first = client.post("/api/v1/runs", json={"scenario_id": SCENARIO_ID})
    second = client.post("/api/v1/runs", json={"scenario_id": SCENARIO_ID})

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["queue_position"] == 1
    assert second.json()["queue_position"] == 2
    assert first.json()["run_id"] != second.json()["run_id"]


def test_create_run_accepts_flat_configuration(client: TestClient) -> None:
    response = client.post(
        "/api/v1/runs",
        json={
            "scenario_id": SCENARIO_ID,
            "fault_config": FAULT_CONFIG,
            "agent_config": {"max_hypotheses": 5},
            "scoring_config": {
                "evidence_weight": 0.5,
                "consistency_weight": 0.3,
                "coverage_weight": 0.2,
            },
        },
    )

    assert response.status_code == 202
    body = response.json()
    run_fault = body["investigation_config"]["fault_config"]
    assert run_fault["fault_type"] == "power_loss"
    assert run_fault["target_subsystem"] == "power"
    assert run_fault["duration_seconds"] == 120
    assert run_fault["magnitude"] == 40
    assert run_fault["start_time"] == "2026-10-30T12:01:00.000Z"
    assert body["investigation_config"]["agent_config"]["max_hypotheses"] == 5
    assert body["fault_config"] == run_fault


def test_create_run_rejects_mixed_config_shapes(client: TestClient) -> None:
    response = client.post(
        "/api/v1/runs",
        json={
            "scenario_id": SCENARIO_ID,
            "investigation_config": {"fault_config": FAULT_CONFIG},
            "fault_config": FAULT_CONFIG,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_run_rejects_invalid_scoring_weights(client: TestClient) -> None:
    response = client.post(
        "/api/v1/runs",
        json={
            "scenario_id": SCENARIO_ID,
            "scoring_config": {
                "evidence_weight": 0.1,
                "consistency_weight": 0.1,
                "coverage_weight": 0.1,
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_run_unknown_scenario_returns_problem(client: TestClient) -> None:
    response = client.post("/api/v1/runs", json={"scenario_id": "scn_missing"})

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_create_run_rejects_invalid_fault(client: TestClient) -> None:
    response = client.post(
        "/api/v1/runs",
        json={
            "scenario_id": SCENARIO_ID,
            "fault_config": {**FAULT_CONFIG, "target_subsystem": "communications"},
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_fault_target"


def test_legacy_unversioned_run_alias(client: TestClient) -> None:
    response = client.post("/api/runs", json={"scenario_id": SCENARIO_ID})

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
