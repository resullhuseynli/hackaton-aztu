"""End-to-end through HTTP: the real FastAPI app on the synthetic network."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings

from .conftest import build_database


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    build_database(db_path)
    # A one-hour tick keeps the background engine asleep; tests advance it by hand.
    settings = Settings(db_path=db_path, source_path=tmp_path / "unused.json", sim_start="08:00",
                        sim_speed=10.0, tick_seconds=3600.0, random_seed=1)
    monkeypatch.setattr(main, "settings", settings)
    with TestClient(main.app) as test_client:
        yield test_client


def advance_minutes(client, minutes):
    engine = client.app.state.container.engine
    for _ in range(minutes * 6):
        engine.step(sim_seconds=10)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_lines_and_line_detail(client):
    lines = client.get("/api/lines").json()
    assert [l["number"] for l in lines] == ["1", "2", "3"]
    detail = client.get("/api/lines/1").json()
    assert detail["line"]["number"] == "1"
    assert [d["direction"] for d in detail["directions"]] == ["forward", "backward"]
    assert len(detail["directions"][0]["stops"]) == 6
    assert len(detail["directions"][0]["route"]) >= 2


def test_unknown_line_is_404(client):
    response = client.get("/api/lines/999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_line_buses_have_live_fields(client):
    buses = client.get("/api/lines/1/buses").json()
    assert len(buses) == 4
    bus = buses[0]
    for field in ("bus_plate", "passenger_count", "passenger_percentage", "passenger_limit",
                  "forwarding_stop_id", "live_latitude", "live_longitude", "density_level", "status"):
        assert field in bus


def test_stop_search_and_detail(client):
    stops = client.get("/api/stops", params={"q": "Xətt 2 dayanacaq 3"}).json()
    assert [s["id"] for s in stops] == [202]
    detail = client.get("/api/stops/202").json()
    assert [l["number"] for l in detail["lines"]] == ["2"]
    assert all(a["line_number"] == "2" for a in detail["arrivals"])


def test_passenger_report(client):
    created = client.post("/api/reports", json={"line_id": 1, "stop_id": 102, "level": "high"})
    assert created.status_code == 201
    assert created.json()["source"] == "passenger"
    assert client.post("/api/reports", json={"line_id": 1, "stop_id": 202, "level": "high"}).status_code == 400
    assert client.post("/api/reports", json={"line_id": 1, "level": "very high"}).status_code == 422


def test_operator_overview_and_density(client):
    advance_minutes(client, 1)
    overview = client.get("/api/operator/overview").json()
    assert overview["active_buses"] == 12
    assert "waiting_passengers" not in overview
    density = client.get("/api/operator/density").json()
    assert len(density) == 3
    assert density == sorted(density, key=lambda d: d["score"], reverse=True)


def test_surge_raises_alert_and_dispatch_resolves_it(client):
    assert client.post("/api/demo/surge/1").status_code == 200
    alert = None
    for minute in range(1, 16):
        advance_minutes(client, 1)
        alerts = client.get("/api/operator/alerts", params={"status": "open"}).json()
        alert = next((a for a in alerts if a["line_id"] == 1), None)
        if alert:
            break
    assert alert is not None, "no alert within 15 minutes of the surge"
    assert 10 <= minute <= 12
    assert alert["type"] == "extra_bus_needed"

    response = client.post(f"/api/operator/alerts/{alert['id']}/dispatch", json={"donor_line_id": 2, "bus_count": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["alert"]["status"] == "resolved"
    assert body["alert"]["resolved_by"] == "operator"
    assert len(body["moved_bus_ids"]) == 1
    assert len(client.get("/api/lines/1/buses").json()) == 5

    again = client.post(f"/api/operator/alerts/{alert['id']}/dispatch", json={"donor_line_id": 2})
    assert again.status_code == 400


def test_websocket_pushes_line_and_operator_data(client):
    with client.websocket_connect("/ws/live?line_id=1&operator=true") as ws:
        message = ws.receive_json()
        assert {"clock", "buses", "overview", "density", "alerts"} <= message.keys()
        assert len(message["buses"]) == 4
        ws.send_json({"line_id": 2})
        message = ws.receive_json()
        assert message["line_id"] == 2
