from collections import defaultdict

from app.domain.enums import Direction
from app.domain.models import Line, LineStop, Network, RoutePoint, Stop

from .database import Database

LINE_COLUMNS = ("id", "number", "carrier", "first_point", "last_point", "route_length_km",
                "duration_minutes", "tariff", "payment_type", "region", "working_zone")


def _line(row) -> Line:
    return Line(**{col: row[col] for col in LINE_COLUMNS})


def _stop(row) -> Stop:
    return Stop(id=row["id"], code=row["code"], name=row["name"], address=row["address"],
                latitude=row["latitude"], longitude=row["longitude"],
                is_transport_hub=bool(row["is_transport_hub"]))


def _line_stop(row) -> LineStop:
    return LineStop(line_id=row["line_id"], stop_id=row["stop_id"], direction=Direction(row["direction"]),
                    stop_order=row["stop_order"], distance_along_m=row["distance_along_m"])


def _route_point(row) -> RoutePoint:
    return RoutePoint(line_id=row["line_id"], direction=Direction(row["direction"]), seq=row["seq"],
                      latitude=row["latitude"], longitude=row["longitude"],
                      distance_along_m=row["distance_along_m"])


class NetworkRepository:
    """Lines, stops, the stops each line serves and the road geometry of each line."""

    def __init__(self, db: Database):
        self.db = db

    def replace(self, network: Network) -> None:
        with self.db.connect() as conn:
            for table in ("route_shapes", "line_stops", "stops", "lines"):
                conn.execute(f"DELETE FROM {table}")
            conn.executemany(
                f"INSERT INTO lines ({', '.join(LINE_COLUMNS)}) VALUES ({', '.join('?' * len(LINE_COLUMNS))})",
                [tuple(getattr(line, col) for col in LINE_COLUMNS) for line in network.lines],
            )
            conn.executemany(
                "INSERT INTO stops VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(s.id, s.code, s.name, s.address, s.latitude, s.longitude, int(s.is_transport_hub))
                 for s in network.stops],
            )
            conn.executemany(
                "INSERT INTO line_stops VALUES (?, ?, ?, ?, ?)",
                [(ls.line_id, ls.stop_id, ls.direction.value, ls.stop_order, ls.distance_along_m)
                 for ls in network.line_stops],
            )
            conn.executemany(
                "INSERT INTO route_shapes VALUES (?, ?, ?, ?, ?, ?)",
                [(p.line_id, p.direction.value, p.seq, p.latitude, p.longitude, p.distance_along_m)
                 for p in network.route_points],
            )

    def list_lines(self, query: str | None = None) -> list[Line]:
        sql = "SELECT * FROM lines"
        params: tuple = ()
        if query:
            sql += " WHERE number LIKE ? OR first_point LIKE ? OR last_point LIKE ?"
            params = (f"{query}%", f"%{query}%", f"%{query}%")
        # Natural order: 1, 2, 10, 10A rather than 1, 10, 10A, 2
        sql += " ORDER BY CAST(number AS INTEGER) = 0, CAST(number AS INTEGER), number"
        with self.db.connect() as conn:
            return [_line(row) for row in conn.execute(sql, params)]

    def get_line(self, line_id: int) -> Line | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM lines WHERE id = ?", (line_id,)).fetchone()
        return _line(row) if row else None

    def get_line_stops(self, line_id: int) -> list[tuple[LineStop, Stop]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT ls.*, s.* FROM line_stops ls JOIN stops s ON s.id = ls.stop_id
                   WHERE ls.line_id = ? ORDER BY ls.direction DESC, ls.stop_order""",
                (line_id,),
            ).fetchall()
        return [(_line_stop(row), _stop(row)) for row in rows]

    def get_route(self, line_id: int) -> dict[Direction, list[RoutePoint]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM route_shapes WHERE line_id = ? ORDER BY direction, seq", (line_id,)
            ).fetchall()
        route: dict[Direction, list[RoutePoint]] = defaultdict(list)
        for row in rows:
            point = _route_point(row)
            route[point.direction].append(point)
        return dict(route)

    def all_routes(self) -> dict[tuple[int, Direction], list[RoutePoint]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM route_shapes ORDER BY line_id, direction, seq").fetchall()
        routes: dict[tuple[int, Direction], list[RoutePoint]] = defaultdict(list)
        for row in rows:
            point = _route_point(row)
            routes[(point.line_id, point.direction)].append(point)
        return dict(routes)

    def all_line_stops(self) -> dict[tuple[int, Direction], list[LineStop]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM line_stops ORDER BY line_id, direction, stop_order").fetchall()
        result: dict[tuple[int, Direction], list[LineStop]] = defaultdict(list)
        for row in rows:
            ls = _line_stop(row)
            result[(ls.line_id, ls.direction)].append(ls)
        return dict(result)

    def line_stops_for_stop(self, stop_id: int) -> list[LineStop]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM line_stops WHERE stop_id = ?", (stop_id,)).fetchall()
        return [_line_stop(row) for row in rows]

    def get_stop(self, stop_id: int) -> Stop | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM stops WHERE id = ?", (stop_id,)).fetchone()
        return _stop(row) if row else None

    def search_stops(self, query: str | None, limit: int = 50) -> list[Stop]:
        sql = "SELECT * FROM stops WHERE latitude IS NOT NULL"
        params: list = []
        if query:
            sql += " AND (name LIKE ? OR code = ?)"
            params += [f"%{query}%", query]
        sql += " ORDER BY name LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            return [_stop(row) for row in conn.execute(sql, params)]

    def stop_lines(self, stop_id: int) -> list[Line]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT l.* FROM lines l JOIN line_stops ls ON ls.line_id = l.id
                   WHERE ls.stop_id = ?
                   ORDER BY CAST(l.number AS INTEGER) = 0, CAST(l.number AS INTEGER), l.number""",
                (stop_id,),
            ).fetchall()
        return [_line(row) for row in rows]

    def line_ids_with_routes(self) -> list[int]:
        with self.db.connect() as conn:
            return [row[0] for row in conn.execute("SELECT DISTINCT line_id FROM line_stops ORDER BY line_id")]
