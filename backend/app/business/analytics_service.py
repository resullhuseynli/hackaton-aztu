"""Density per line and the anomaly rule: a line that stays "high" for 10 minutes needs extra buses.

Works only from the repositories (bus positions/loads and passenger reports), so it does not care
whether the data comes from the simulator or real feeds.
"""
from datetime import datetime, timedelta

from app.domain import rules
from app.domain.enums import AlertStatus, AlertType, BusStatus, DensityLevel
from app.domain.geo import haversine_m
from app.domain.models import Alert, DensitySnapshot
from app.repository import AlertRepository, BusRepository, DensityRepository, NetworkRepository, ReportRepository

LEVEL_LABELS = {DensityLevel.LOW: "Aşağı", DensityLevel.MEDIUM: "Orta", DensityLevel.HIGH: "Yüksək"}
MIN_DONOR_BUSES = 3
DONOR_RADIUS_M = 8_000  # route centroids this close count as "nearby"


class AnalyticsService:
    def __init__(self, network_repo: NetworkRepository, bus_repo: BusRepository, report_repo: ReportRepository,
                 density_repo: DensityRepository, alert_repo: AlertRepository,
                 alert_window: timedelta, resolve_window: timedelta, report_window: timedelta):
        self.network_repo = network_repo
        self.bus_repo = bus_repo
        self.report_repo = report_repo
        self.density_repo = density_repo
        self.alert_repo = alert_repo
        self.alert_window = alert_window
        self.resolve_window = resolve_window
        self.report_window = report_window
        self._centroids: dict[int, tuple[float, float]] | None = None

    def run(self, now: datetime) -> list[Alert]:
        snapshots = self.compute_density(now)
        self.density_repo.add_many(snapshots)
        return self.evaluate_alerts(now, snapshots)

    def compute_density(self, now: datetime) -> list[DensitySnapshot]:
        loads: dict[int, list[float]] = {}
        for bus in self.bus_repo.list_all():
            loads.setdefault(bus.line_id, [])
            # Empty buses on a terminal break say nothing about how crowded the line is.
            if bus.status == BusStatus.IN_SERVICE:
                loads[bus.line_id].append(bus.passenger_percentage)
        reports = self.report_repo.levels_by_line(now - self.report_window)
        snapshots = []
        for line_id, percentages in loads.items():
            occupancy = round(sum(percentages) / len(percentages), 1) if percentages else 0.0
            line_reports = reports.get(line_id, [])
            reported = rules.report_score(line_reports)
            score = rules.density_score(occupancy, reported, len(line_reports))
            snapshots.append(DensitySnapshot(
                line_id=line_id, occupancy_pct=occupancy,
                report_score=round(reported, 1) if reported is not None else None,
                score=score, level=rules.density_level(score), active_buses=len(percentages), computed_at=now,
            ))
        return snapshots

    def evaluate_alerts(self, now: datetime, snapshots: list[DensitySnapshot]) -> list[Alert]:
        lookback = max(self.alert_window, self.resolve_window) + timedelta(minutes=2)
        history = self.density_repo.recent_levels(now - lookback)
        open_lines = self.alert_repo.open_line_ids()
        by_line = {s.line_id: s for s in snapshots}
        created = []
        for snapshot in snapshots:
            levels = history.get(snapshot.line_id, [])
            if snapshot.line_id in open_lines:
                if rules.is_sustained(levels, now, self.resolve_window, lambda level: level != DensityLevel.HIGH):
                    self.alert_repo.resolve_for_line(snapshot.line_id, now, "system")
            elif rules.is_sustained(levels, now, self.alert_window, lambda level: level == DensityLevel.HIGH):
                alert = self._extra_bus_alert(snapshot, by_line, open_lines, now)
                created.append(self.alert_repo.create(alert))
                open_lines.add(snapshot.line_id)
        return created

    def _extra_bus_alert(self, snapshot: DensitySnapshot, by_line: dict[int, DensitySnapshot],
                         open_lines: set[int], now: datetime) -> Alert:
        line = self.network_repo.get_line(snapshot.line_id)
        count = rules.suggested_extra_buses(snapshot.score, snapshot.active_buses)
        donor = self._find_donor(snapshot.line_id, by_line, open_lines, count)
        minutes = int(self.alert_window.total_seconds() // 60)
        message = (f"Xətt {line.number}: sıxlıq {minutes} dəqiqədir \"{LEVEL_LABELS[DensityLevel.HIGH]}\" "
                   f"səviyyədədir ({snapshot.score:.0f}%). Əlavə avtobus ehtiyatı ayrılmalıdır "
                   f"(tövsiyə: {count} avtobus).")
        if donor:
            donor_line = self.network_repo.get_line(donor.line_id)
            message += (f" Yaxınlıqdakı az yüklü xətdən yönləndirilə bilər: Xətt {donor_line.number} "
                        f"(doluluq {donor.occupancy_pct:.0f}%).")
        return Alert(
            line_id=snapshot.line_id, type=AlertType.EXTRA_BUS_NEEDED, message=message, status=AlertStatus.OPEN,
            created_at=now, suggested_bus_count=count, suggested_donor_line_id=donor.line_id if donor else None,
        )

    def _find_donor(self, line_id: int, by_line: dict[int, DensitySnapshot], open_lines: set[int],
                    count: int) -> DensitySnapshot | None:
        """The emptiest low-density line nearby that can spare the buses (nearest one if none is close)."""
        centroids = self._line_centroids()
        target = centroids.get(line_id)
        candidates = [
            s for s in by_line.values()
            if s.line_id != line_id and s.line_id not in open_lines and s.level == DensityLevel.LOW
            and s.active_buses - count >= MIN_DONOR_BUSES - 1 and s.line_id in centroids
        ]
        if not candidates or not target:
            return None
        distance = {s.line_id: haversine_m(*target, *centroids[s.line_id]) for s in candidates}
        nearby = [s for s in candidates if distance[s.line_id] <= DONOR_RADIUS_M]
        if nearby:
            return min(nearby, key=lambda s: s.score)
        return min(candidates, key=lambda s: distance[s.line_id])

    def _line_centroids(self) -> dict[int, tuple[float, float]]:
        if self._centroids is None:
            centroids = {}
            for (line_id, _), points in self.network_repo.all_routes().items():
                if line_id not in centroids:
                    centroids[line_id] = (sum(p.latitude for p in points) / len(points),
                                          sum(p.longitude for p in points) / len(points))
            self._centroids = centroids
        return self._centroids
