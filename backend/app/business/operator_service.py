from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.enums import AlertStatus, DensityLevel
from app.domain.models import Alert, Bus, DensitySnapshot, Line
from app.repository import AlertRepository, BusRepository, DensityRepository, NetworkRepository, ReportRepository

from .clock import SimulationClock
from .errors import NotFoundError, ValidationError
from .simulation_service import SimulationService

TREND_WINDOW = timedelta(minutes=10)
TREND_THRESHOLD = 3.0


@dataclass
class LineDensity:
    line: Line
    snapshot: DensitySnapshot
    trend: str                 # "up" | "down" | "flat"
    reports_last_window: int
    waiting_passengers: int
    has_open_alert: bool


@dataclass
class AlertView:
    alert: Alert
    line_number: str
    donor_line_number: str | None


@dataclass
class Overview:
    clock: datetime
    active_buses: int
    average_occupancy: float
    lines_by_level: dict[DensityLevel, int]
    open_alerts: int
    waiting_passengers: int
    reports_last_window: int


@dataclass
class DispatchResult:
    alert: AlertView
    moved_bus_ids: list[int]


class OperatorService:
    def __init__(self, clock: SimulationClock, network_repo: NetworkRepository, bus_repo: BusRepository,
                 report_repo: ReportRepository, density_repo: DensityRepository, alert_repo: AlertRepository,
                 simulation: SimulationService, report_window: timedelta):
        self.clock = clock
        self.network_repo = network_repo
        self.bus_repo = bus_repo
        self.report_repo = report_repo
        self.density_repo = density_repo
        self.alert_repo = alert_repo
        self.simulation = simulation
        self.report_window = report_window

    def overview(self) -> Overview:
        now = self.clock.now()
        latest = self.density_repo.latest()
        buses = self.bus_repo.list_all()
        levels = {level: 0 for level in DensityLevel}
        for snapshot in latest:
            levels[snapshot.level] += 1
        return Overview(
            clock=now,
            active_buses=len(buses),
            average_occupancy=round(sum(b.passenger_percentage for b in buses) / len(buses), 1) if buses else 0.0,
            lines_by_level=levels,
            open_alerts=len(self.alert_repo.open_line_ids()),
            waiting_passengers=sum(self.simulation.waiting_by_line().values()),
            reports_last_window=sum(self.report_repo.count_by_line(now - self.report_window).values()),
        )

    def density(self, level: DensityLevel | None = None) -> list[LineDensity]:
        now = self.clock.now()
        latest = self.density_repo.latest()
        if not latest:
            return []
        past = self.density_repo.scores_at(now - TREND_WINDOW)
        reports = self.report_repo.count_by_line(now - self.report_window)
        waiting = self.simulation.waiting_by_line()
        open_lines = self.alert_repo.open_line_ids()
        lines = {line.id: line for line in self.network_repo.list_lines()}
        result = []
        for snapshot in latest:
            if level and snapshot.level != level:
                continue
            before = past.get(snapshot.line_id)
            if before is None or abs(snapshot.score - before) < TREND_THRESHOLD:
                trend = "flat"
            else:
                trend = "up" if snapshot.score > before else "down"
            result.append(LineDensity(
                line=lines[snapshot.line_id], snapshot=snapshot, trend=trend,
                reports_last_window=reports.get(snapshot.line_id, 0),
                waiting_passengers=waiting.get(snapshot.line_id, 0),
                has_open_alert=snapshot.line_id in open_lines,
            ))
        result.sort(key=lambda d: d.snapshot.score, reverse=True)
        return result

    def fleet(self) -> list[tuple[Bus, str]]:
        """Every bus with its line number, for the network-wide density map."""
        numbers = {line.id: line.number for line in self.network_repo.list_lines()}
        return [(bus, numbers[bus.line_id]) for bus in self.bus_repo.list_all()]

    def history(self, line_id: int, minutes: int = 60) -> tuple[Line, list[DensitySnapshot]]:
        line = self._line(line_id)
        return line, self.density_repo.history(line_id, self.clock.now() - timedelta(minutes=minutes))

    def alerts(self, status: AlertStatus | None = None, limit: int = 100) -> list[AlertView]:
        return [self._view(alert) for alert in self.alert_repo.list(status, limit)]

    def resolve(self, alert_id: int) -> AlertView:
        alert = self._alert(alert_id)
        self.alert_repo.resolve(alert_id, self.clock.now(), "operator")
        return self._view(self.alert_repo.get(alert.id))

    def dispatch(self, alert_id: int, donor_line_id: int | None = None, bus_count: int | None = None) -> DispatchResult:
        """Act on an alert: move buses from the donor line to the overcrowded line, then close the alert."""
        alert = self._alert(alert_id)
        if alert.status != AlertStatus.OPEN:
            raise ValidationError("Alert is already resolved")
        donor = donor_line_id or alert.suggested_donor_line_id
        if not donor:
            raise ValidationError("No donor line suggested; pass donor_line_id")
        if donor == alert.line_id:
            raise ValidationError("Donor line must differ from the alert line")
        self._line(donor)
        moved = self.simulation.reassign(donor, alert.line_id, bus_count or alert.suggested_bus_count)
        if not moved:
            raise ValidationError("Donor line has no buses to spare")
        self.alert_repo.resolve(alert_id, self.clock.now(), "operator")
        return DispatchResult(alert=self._view(self.alert_repo.get(alert_id)), moved_bus_ids=moved)

    def surge(self, line_id: int) -> Line:
        line = self._line(line_id)
        if not self.simulation.surge(line_id):
            raise ValidationError(f"Line {line.number} has no buses in the simulation")
        return line

    def _view(self, alert: Alert) -> AlertView:
        donor = self.network_repo.get_line(alert.suggested_donor_line_id) if alert.suggested_donor_line_id else None
        return AlertView(alert=alert, line_number=self._line(alert.line_id).number,
                         donor_line_number=donor.number if donor else None)

    def _alert(self, alert_id: int) -> Alert:
        alert = self.alert_repo.get(alert_id)
        if not alert:
            raise NotFoundError(f"Alert {alert_id} not found")
        return alert

    def _line(self, line_id: int) -> Line:
        line = self.network_repo.get_line(line_id)
        if not line:
            raise NotFoundError(f"Line {line_id} not found")
        return line
