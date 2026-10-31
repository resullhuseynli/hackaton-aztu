"""Shared fixtures: a tiny synthetic network in a temporary SQLite database.

Three parallel east-west lines (~8.5 km, 6 stops each) a kilometre apart in Baku, so tests
never touch the real database or the network.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.business.ingestion_service import FleetService, NetworkImportService
from app.repository import (AlertRepository, BusRepository, Database, DensityRepository, MaintenanceRepository,
                            NetworkRepository, ReportRepository)

LNG_FROM, LNG_TO = 49.80, 49.90
START = datetime(2026, 10, 31, 8, 0, 0)


def points(lat: float, count: int) -> list[tuple[float, float]]:
    step = (LNG_TO - LNG_FROM) / (count - 1)
    return [(lat, round(LNG_FROM + i * step, 6)) for i in range(count)]


def source_line(line_id: int, number: str, lat: float, first_stop_id: int, stop_count: int = 6) -> dict:
    stops = [
        {"stopId": first_stop_id + i, "code": f"{first_stop_id + i}", "name": f"Xətt {number} dayanacaq {i + 1}",
         "address": f"Küçə {i + 1}", "latitude": la, "longitude": lo, "isTransportHub": False}
        for i, (la, lo) in enumerate(points(lat, stop_count))
    ]
    shape = [[la, lo] for la, lo in points(lat, 30)]
    return {
        "id": line_id, "number": number, "carrier": "Test MMC", "firstPoint": stops[0]["name"],
        "lastPoint": stops[-1]["name"], "routeLengthKm": 8.5, "durationMinutes": 30, "tariff": "0.60 AZN",
        "paymentType": "Kart", "region": "Bakı", "workingZone": "Şəhərdaxili",
        "stops": {"forward": stops, "backward": list(reversed(stops))},
        "shapes": {"forward": shape, "backward": list(reversed(shape))},
    }


def make_source() -> dict:
    return {"lines": [
        source_line(1, "1", 40.400, 100),
        source_line(2, "2", 40.410, 200),
        source_line(3, "3", 40.420, 300),
    ]}


def build_database(path) -> Database:
    db = Database(path)
    db.recreate()
    network_repo = NetworkRepository(db)
    NetworkImportService(network_repo).import_source(make_source())
    FleetService(network_repo, BusRepository(db), seed=1).generate()
    return db


@pytest.fixture
def db(tmp_path) -> Database:
    return build_database(tmp_path / "test.db")


@pytest.fixture
def repos(db) -> SimpleNamespace:
    return SimpleNamespace(
        network=NetworkRepository(db), buses=BusRepository(db), reports=ReportRepository(db),
        density=DensityRepository(db), alerts=AlertRepository(db), maintenance=MaintenanceRepository(db),
    )
