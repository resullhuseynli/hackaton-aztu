from datetime import datetime

from app.domain.enums import BusStatus, Direction
from app.domain.models import Bus

from .database import Database, from_db_time, to_db_time


def _bus(row) -> Bus:
    return Bus(
        bus_id=row["bus_id"], line_id=row["line_id"], bus_plate=row["bus_plate"],
        passenger_limit=row["passenger_limit"], direction=Direction(row["direction"]),
        passenger_count=row["passenger_count"], forwarding_stop_id=row["forwarding_stop_id"],
        live_latitude=row["live_latitude"], live_longitude=row["live_longitude"],
        position_m=row["position_m"], speed_kmh=row["speed_kmh"], status=BusStatus(row["status"]),
        updated_at=from_db_time(row["updated_at"]),
    )


def _live_values(bus: Bus) -> tuple:
    return (bus.line_id, bus.direction.value, bus.passenger_count, bus.forwarding_stop_id,
            bus.live_latitude, bus.live_longitude, bus.position_m, bus.speed_kmh, bus.status.value,
            to_db_time(bus.updated_at), bus.bus_id)


class BusRepository:
    def __init__(self, db: Database):
        self.db = db

    def replace_fleet(self, buses: list[Bus]) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM buses")
            conn.executemany(
                """INSERT INTO buses (bus_id, line_id, bus_plate, passenger_limit, direction, passenger_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(b.bus_id, b.line_id, b.bus_plate, b.passenger_limit, b.direction.value, b.passenger_count)
                 for b in buses],
            )

    def list_all(self) -> list[Bus]:
        with self.db.connect() as conn:
            return [_bus(row) for row in conn.execute("SELECT * FROM buses ORDER BY bus_id")]

    def list_by_line(self, line_id: int) -> list[Bus]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM buses WHERE line_id = ? ORDER BY bus_id", (line_id,))
            return [_bus(row) for row in rows]

    def get(self, bus_id: int) -> Bus | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM buses WHERE bus_id = ?", (bus_id,)).fetchone()
        return _bus(row) if row else None

    def save_live_state(self, buses: list[Bus]) -> None:
        with self.db.connect() as conn:
            conn.executemany(
                """UPDATE buses SET line_id = ?, direction = ?, passenger_count = ?, forwarding_stop_id = ?,
                       live_latitude = ?, live_longitude = ?, position_m = ?, speed_kmh = ?, status = ?, updated_at = ?
                   WHERE bus_id = ?""",
                [_live_values(b) for b in buses],
            )

    def record_telemetry(self, buses: list[Bus], recorded_at: datetime) -> None:
        stamp = to_db_time(recorded_at)
        with self.db.connect() as conn:
            conn.executemany(
                """INSERT INTO bus_telemetry (bus_id, line_id, latitude, longitude, passenger_count, speed_kmh, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [(b.bus_id, b.line_id, b.live_latitude, b.live_longitude, b.passenger_count, b.speed_kmh, stamp)
                 for b in buses],
            )

    def average_speed_kmh(self, since: datetime) -> dict[int, float]:
        """Average recent driving speed per bus (stops excluded), used to smooth ETA estimates."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT bus_id, AVG(speed_kmh) FROM bus_telemetry
                   WHERE recorded_at >= ? AND speed_kmh > 0 GROUP BY bus_id""",
                (to_db_time(since),),
            )
            return {row[0]: row[1] for row in rows}
