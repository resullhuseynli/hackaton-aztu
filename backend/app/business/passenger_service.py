from dataclasses import dataclass

from app.domain import rules
from app.domain.enums import DensityLevel, Direction, ReportSource
from app.domain.models import Arrival, Bus, CrowdReport, Line, LineStop, RoutePoint, Stop
from app.repository import BusRepository, DensityRepository, NetworkRepository, ReportRepository

from .clock import SimulationClock
from .errors import NotFoundError, ValidationError
from .eta_service import EtaService


@dataclass
class LineSummary:
    line: Line
    active_buses: int
    density_level: DensityLevel | None
    density_score: float | None


@dataclass
class LineDetail:
    line: Line
    stops: dict[Direction, list[tuple[LineStop, Stop]]]
    route: dict[Direction, list[RoutePoint]]


@dataclass
class LiveBus:
    bus: Bus
    density_level: DensityLevel
    next_stop_name: str | None
    next_stop_eta_seconds: int | None


@dataclass
class StopDetail:
    stop: Stop
    lines: list[Line]
    arrivals: list[Arrival]


class PassengerService:
    def __init__(self, clock: SimulationClock, network_repo: NetworkRepository, bus_repo: BusRepository,
                 report_repo: ReportRepository, density_repo: DensityRepository, eta_service: EtaService):
        self.clock = clock
        self.network_repo = network_repo
        self.bus_repo = bus_repo
        self.report_repo = report_repo
        self.density_repo = density_repo
        self.eta_service = eta_service

    def list_lines(self, query: str | None = None) -> list[LineSummary]:
        density = {s.line_id: s for s in self.density_repo.latest()}
        result = []
        for line in self.network_repo.list_lines(query):
            snapshot = density.get(line.id)
            result.append(LineSummary(
                line=line,
                active_buses=snapshot.active_buses if snapshot else 0,
                density_level=snapshot.level if snapshot else None,
                density_score=snapshot.score if snapshot else None,
            ))
        return result

    def line_detail(self, line_id: int) -> LineDetail:
        line = self._line(line_id)
        stops: dict[Direction, list[tuple[LineStop, Stop]]] = {d: [] for d in Direction}
        for line_stop, stop in self.network_repo.get_line_stops(line_id):
            stops[line_stop.direction].append((line_stop, stop))
        return LineDetail(line=line, stops=stops, route=self.network_repo.get_route(line_id))

    def line_buses(self, line_id: int) -> list[LiveBus]:
        self._line(line_id)
        buses = self.bus_repo.list_by_line(line_id)
        etas = self.eta_service.next_stop_eta(buses, self.clock.now())
        stop_names = {stop.id: stop.name for _, stop in self.network_repo.get_line_stops(line_id)}
        return [
            LiveBus(
                bus=bus,
                density_level=rules.density_level(bus.passenger_percentage),
                next_stop_name=stop_names.get(bus.forwarding_stop_id),
                next_stop_eta_seconds=etas.get(bus.bus_id),
            )
            for bus in buses
        ]

    def search_stops(self, query: str | None, limit: int = 50) -> list[Stop]:
        return self.network_repo.search_stops(query, limit)

    def stop_detail(self, stop_id: int) -> StopDetail:
        stop = self.network_repo.get_stop(stop_id)
        if not stop:
            raise NotFoundError(f"Stop {stop_id} not found")
        return StopDetail(
            stop=stop,
            lines=self.network_repo.stop_lines(stop_id),
            arrivals=self.eta_service.arrivals_at_stop(stop_id, self.clock.now()),
        )

    def submit_report(self, line_id: int, level: DensityLevel, stop_id: int | None, bus_id: int | None) -> CrowdReport:
        self._line(line_id)
        if stop_id is not None:
            if not any(ls.line_id == line_id for ls in self.network_repo.line_stops_for_stop(stop_id)):
                raise ValidationError(f"Stop {stop_id} is not served by line {line_id}")
        if bus_id is not None:
            bus = self.bus_repo.get(bus_id)
            if not bus or bus.line_id != line_id:
                raise ValidationError(f"Bus {bus_id} is not running on line {line_id}")
        report = CrowdReport(line_id=line_id, level=level, reported_at=self.clock.now(),
                             source=ReportSource.PASSENGER, stop_id=stop_id, bus_id=bus_id)
        return self.report_repo.add(report)

    def _line(self, line_id: int) -> Line:
        line = self.network_repo.get_line(line_id)
        if not line:
            raise NotFoundError(f"Line {line_id} not found")
        return line
