from collections import defaultdict
from datetime import datetime

from app.domain.enums import AlertStatus, AlertType, DensityLevel, ReportSource
from app.domain.models import Alert, CrowdReport, DensitySnapshot

from .database import Database, from_db_time, to_db_time


def _snapshot(row) -> DensitySnapshot:
    return DensitySnapshot(
        line_id=row["line_id"], occupancy_pct=row["occupancy_pct"], report_score=row["report_score"],
        score=row["score"], level=DensityLevel(row["level"]), active_buses=row["active_buses"],
        computed_at=from_db_time(row["computed_at"]),
    )


def _alert(row) -> Alert:
    return Alert(
        id=row["id"], line_id=row["line_id"], type=AlertType(row["type"]), message=row["message"],
        status=AlertStatus(row["status"]), created_at=from_db_time(row["created_at"]),
        suggested_bus_count=row["suggested_bus_count"], suggested_donor_line_id=row["suggested_donor_line_id"],
        resolved_at=from_db_time(row["resolved_at"]), resolved_by=row["resolved_by"],
    )


class ReportRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, report: CrowdReport) -> CrowdReport:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO crowd_reports (line_id, stop_id, bus_id, level, source, reported_at) VALUES (?, ?, ?, ?, ?, ?)",
                (report.line_id, report.stop_id, report.bus_id, report.level.value, report.source.value,
                 to_db_time(report.reported_at)),
            )
            report.id = cur.lastrowid
        return report

    def add_many(self, reports: list[CrowdReport]) -> None:
        with self.db.connect() as conn:
            conn.executemany(
                "INSERT INTO crowd_reports (line_id, stop_id, bus_id, level, source, reported_at) VALUES (?, ?, ?, ?, ?, ?)",
                [(r.line_id, r.stop_id, r.bus_id, r.level.value, r.source.value, to_db_time(r.reported_at))
                 for r in reports],
            )

    def levels_by_line(self, since: datetime) -> dict[int, list[DensityLevel]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT line_id, level FROM crowd_reports WHERE reported_at >= ?", (to_db_time(since),)
            )
            result: dict[int, list[DensityLevel]] = defaultdict(list)
            for row in rows:
                result[row["line_id"]].append(DensityLevel(row["level"]))
            return dict(result)

    def count_by_line(self, since: datetime) -> dict[int, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT line_id, COUNT(*) FROM crowd_reports WHERE reported_at >= ? GROUP BY line_id",
                (to_db_time(since),),
            )
            return {row[0]: row[1] for row in rows}


class DensityRepository:
    def __init__(self, db: Database):
        self.db = db

    def add_many(self, snapshots: list[DensitySnapshot]) -> None:
        with self.db.connect() as conn:
            conn.executemany(
                """INSERT INTO line_density (line_id, occupancy_pct, report_score, score, level, active_buses, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [(s.line_id, s.occupancy_pct, s.report_score, s.score, s.level.value, s.active_buses,
                  to_db_time(s.computed_at)) for s in snapshots],
            )

    def latest(self) -> list[DensitySnapshot]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM line_density
                   WHERE computed_at = (SELECT MAX(computed_at) FROM line_density)"""
            )
            return [_snapshot(row) for row in rows]

    def scores_at(self, moment: datetime) -> dict[int, float]:
        """Score per line from the first snapshot round at or after `moment`."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT line_id, score FROM line_density
                   WHERE computed_at = (SELECT MIN(computed_at) FROM line_density WHERE computed_at >= ?)""",
                (to_db_time(moment),),
            )
            return {row[0]: row[1] for row in rows}

    def history(self, line_id: int, since: datetime) -> list[DensitySnapshot]:
        """Snapshots of one line since `since`, oldest first."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM line_density WHERE line_id = ? AND computed_at >= ? ORDER BY computed_at",
                (line_id, to_db_time(since)),
            )
            return [_snapshot(row) for row in rows]

    def recent_levels(self, since: datetime) -> dict[int, list[tuple[datetime, DensityLevel]]]:
        """(computed_at, level) per line since `since`, newest first."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT line_id, computed_at, level FROM line_density WHERE computed_at >= ? ORDER BY computed_at DESC",
                (to_db_time(since),),
            )
            result: dict[int, list[tuple[datetime, DensityLevel]]] = defaultdict(list)
            for row in rows:
                result[row["line_id"]].append((from_db_time(row["computed_at"]), DensityLevel(row["level"])))
            return dict(result)


class AlertRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, alert: Alert) -> Alert:
        with self.db.connect() as conn:
            cur = conn.execute(
                """INSERT INTO alerts (line_id, type, message, suggested_bus_count, suggested_donor_line_id, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (alert.line_id, alert.type.value, alert.message, alert.suggested_bus_count,
                 alert.suggested_donor_line_id, alert.status.value, to_db_time(alert.created_at)),
            )
            alert.id = cur.lastrowid
        return alert

    def get(self, alert_id: int) -> Alert | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return _alert(row) if row else None

    def list(self, status: AlertStatus | None = None, limit: int = 100) -> list[Alert]:
        sql, params = "SELECT * FROM alerts", []
        if status:
            sql += " WHERE status = ?"
            params.append(status.value)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            return [_alert(row) for row in conn.execute(sql, params)]

    def open_line_ids(self) -> set[int]:
        with self.db.connect() as conn:
            return {row[0] for row in conn.execute("SELECT line_id FROM alerts WHERE status = 'open'")}

    def resolve(self, alert_id: int, resolved_at: datetime, resolved_by: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE alerts SET status = 'resolved', resolved_at = ?, resolved_by = ? WHERE id = ? AND status = 'open'",
                (to_db_time(resolved_at), resolved_by, alert_id),
            )

    def resolve_for_line(self, line_id: int, resolved_at: datetime, resolved_by: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE alerts SET status = 'resolved', resolved_at = ?, resolved_by = ? WHERE line_id = ? AND status = 'open'",
                (to_db_time(resolved_at), resolved_by, line_id),
            )


class MaintenanceRepository:
    def __init__(self, db: Database):
        self.db = db

    def clear_live_data(self) -> None:
        with self.db.connect() as conn:
            for table in ("alerts", "line_density", "crowd_reports", "bus_telemetry"):
                conn.execute(f"DELETE FROM {table}")

    def prune(self, before: datetime) -> None:
        stamp = to_db_time(before)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM bus_telemetry WHERE recorded_at < ?", (stamp,))
            conn.execute("DELETE FROM crowd_reports WHERE reported_at < ?", (stamp,))
            conn.execute("DELETE FROM line_density WHERE computed_at < ?", (stamp,))
