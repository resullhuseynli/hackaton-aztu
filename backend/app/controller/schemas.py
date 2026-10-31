"""Request/response models of the HTTP API and their mapping from domain/business objects."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.business.operator_service import AlertView, DispatchResult, LineDensity, Overview
from app.business.passenger_service import LineDetail, LineSummary, LiveBus, StopDetail
from app.domain import rules
from app.domain.enums import AlertStatus, AlertType, BusStatus, DensityLevel, Direction, ReportSource
from app.domain.models import Arrival, Bus, CrowdReport, DensitySnapshot, Line, LineStop, Stop


class LineOut(BaseModel):
    id: int
    number: str
    carrier: str | None
    first_point: str | None
    last_point: str | None
    route_length_km: float | None
    duration_minutes: int | None
    tariff: str | None
    payment_type: str | None
    region: str | None
    working_zone: str | None

    @classmethod
    def of(cls, line: Line) -> "LineOut":
        return cls(**line.__dict__)


class LineSummaryOut(LineOut):
    active_buses: int
    density_level: DensityLevel | None
    density_score: float | None

    @classmethod
    def of_summary(cls, summary: LineSummary) -> "LineSummaryOut":
        return cls(**summary.line.__dict__, active_buses=summary.active_buses,
                   density_level=summary.density_level, density_score=summary.density_score)


class StopOut(BaseModel):
    id: int
    code: str | None
    name: str
    address: str | None
    latitude: float | None
    longitude: float | None
    is_transport_hub: bool

    @classmethod
    def of(cls, stop: Stop) -> "StopOut":
        return cls(**stop.__dict__)


class LineStopOut(StopOut):
    stop_order: int
    distance_along_m: float

    @classmethod
    def of_pair(cls, line_stop: LineStop, stop: Stop) -> "LineStopOut":
        return cls(**stop.__dict__, stop_order=line_stop.stop_order, distance_along_m=line_stop.distance_along_m)


class DirectionOut(BaseModel):
    direction: Direction
    stops: list[LineStopOut]
    route: list[tuple[float, float]] = Field(description="Road geometry as [latitude, longitude] pairs")


class LineDetailOut(BaseModel):
    line: LineOut
    directions: list[DirectionOut]

    @classmethod
    def of(cls, detail: LineDetail) -> "LineDetailOut":
        return cls(
            line=LineOut.of(detail.line),
            directions=[
                DirectionOut(
                    direction=direction,
                    stops=[LineStopOut.of_pair(ls, s) for ls, s in detail.stops[direction]],
                    route=[(p.latitude, p.longitude) for p in detail.route.get(direction, [])],
                )
                for direction in Direction if detail.stops[direction]
            ],
        )


class LiveBusOut(BaseModel):
    bus_id: int
    line_id: int
    bus_plate: str
    direction: Direction
    passenger_count: int
    passenger_limit: int
    passenger_percentage: float
    density_level: DensityLevel
    forwarding_stop_id: int | None
    next_stop_name: str | None
    next_stop_eta_seconds: int | None
    live_latitude: float | None
    live_longitude: float | None
    speed_kmh: float
    status: BusStatus
    updated_at: datetime | None

    @classmethod
    def of(cls, live: LiveBus) -> "LiveBusOut":
        bus = live.bus
        return cls(
            bus_id=bus.bus_id, line_id=bus.line_id, bus_plate=bus.bus_plate, direction=bus.direction,
            passenger_count=bus.passenger_count, passenger_limit=bus.passenger_limit,
            passenger_percentage=bus.passenger_percentage, density_level=live.density_level,
            forwarding_stop_id=bus.forwarding_stop_id, next_stop_name=live.next_stop_name,
            next_stop_eta_seconds=live.next_stop_eta_seconds, live_latitude=bus.live_latitude,
            live_longitude=bus.live_longitude, speed_kmh=bus.speed_kmh, status=bus.status, updated_at=bus.updated_at,
        )


class ArrivalOut(BaseModel):
    bus_id: int
    bus_plate: str
    line_id: int
    line_number: str
    direction: Direction
    eta_seconds: int
    distance_m: float
    stops_away: int
    passenger_percentage: float
    density_level: DensityLevel
    latitude: float | None
    longitude: float | None

    @classmethod
    def of(cls, arrival: Arrival) -> "ArrivalOut":
        return cls(**arrival.__dict__)


class StopDetailOut(BaseModel):
    stop: StopOut
    lines: list[LineOut]
    arrivals: list[ArrivalOut]

    @classmethod
    def of(cls, detail: StopDetail) -> "StopDetailOut":
        return cls(stop=StopOut.of(detail.stop), lines=[LineOut.of(l) for l in detail.lines],
                   arrivals=[ArrivalOut.of(a) for a in detail.arrivals])


class ReportIn(BaseModel):
    line_id: int
    level: DensityLevel
    stop_id: int | None = None
    bus_id: int | None = None


class ReportOut(BaseModel):
    id: int
    line_id: int
    stop_id: int | None
    bus_id: int | None
    level: DensityLevel
    source: ReportSource
    reported_at: datetime

    @classmethod
    def of(cls, report: CrowdReport) -> "ReportOut":
        return cls(**report.__dict__)


# ---- operator ----------------------------------------------------------------------------------

class OverviewOut(BaseModel):
    clock: datetime
    active_buses: int
    average_occupancy: float
    lines_by_level: dict[DensityLevel, int]
    open_alerts: int
    waiting_passengers: int
    reports_last_window: int

    @classmethod
    def of(cls, overview: Overview) -> "OverviewOut":
        return cls(**overview.__dict__)


class LineDensityOut(BaseModel):
    line_id: int
    line_number: str
    first_point: str | None
    last_point: str | None
    occupancy_pct: float
    report_score: float | None
    score: float
    level: DensityLevel
    active_buses: int
    trend: str
    reports_last_window: int
    waiting_passengers: int
    has_open_alert: bool
    computed_at: datetime

    @classmethod
    def of(cls, d: LineDensity) -> "LineDensityOut":
        s = d.snapshot
        return cls(
            line_id=d.line.id, line_number=d.line.number, first_point=d.line.first_point,
            last_point=d.line.last_point, occupancy_pct=s.occupancy_pct, report_score=s.report_score,
            score=s.score, level=s.level, active_buses=s.active_buses, trend=d.trend,
            reports_last_window=d.reports_last_window, waiting_passengers=d.waiting_passengers,
            has_open_alert=d.has_open_alert, computed_at=s.computed_at,
        )


class FleetBusOut(BaseModel):
    bus_id: int
    line_id: int
    line_number: str
    latitude: float | None
    longitude: float | None
    passenger_percentage: float
    density_level: DensityLevel
    status: BusStatus

    @classmethod
    def of(cls, bus: Bus, line_number: str) -> "FleetBusOut":
        return cls(bus_id=bus.bus_id, line_id=bus.line_id, line_number=line_number, latitude=bus.live_latitude,
                   longitude=bus.live_longitude, passenger_percentage=bus.passenger_percentage,
                   density_level=rules.density_level(bus.passenger_percentage), status=bus.status)


class DensityPointOut(BaseModel):
    computed_at: datetime
    score: float
    occupancy_pct: float
    report_score: float | None
    level: DensityLevel

    @classmethod
    def of(cls, s: DensitySnapshot) -> "DensityPointOut":
        return cls(computed_at=s.computed_at, score=s.score, occupancy_pct=s.occupancy_pct,
                   report_score=s.report_score, level=s.level)


class DensityHistoryOut(BaseModel):
    line_id: int
    line_number: str
    points: list[DensityPointOut]


class AlertOut(BaseModel):
    id: int
    line_id: int
    line_number: str
    type: AlertType
    message: str
    status: AlertStatus
    suggested_bus_count: int
    suggested_donor_line_id: int | None
    donor_line_number: str | None
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None

    @classmethod
    def of(cls, view: AlertView) -> "AlertOut":
        a = view.alert
        return cls(
            id=a.id, line_id=a.line_id, line_number=view.line_number, type=a.type, message=a.message,
            status=a.status, suggested_bus_count=a.suggested_bus_count,
            suggested_donor_line_id=a.suggested_donor_line_id, donor_line_number=view.donor_line_number,
            created_at=a.created_at, resolved_at=a.resolved_at, resolved_by=a.resolved_by,
        )


class DispatchIn(BaseModel):
    donor_line_id: int | None = None
    bus_count: int | None = Field(default=None, ge=1, le=10)


class DispatchOut(BaseModel):
    alert: AlertOut
    moved_bus_ids: list[int]

    @classmethod
    def of(cls, result: DispatchResult) -> "DispatchOut":
        return cls(alert=AlertOut.of(result.alert), moved_bus_ids=result.moved_bus_ids)


class SimulationOut(BaseModel):
    clock: datetime
    speed: float
    tick_seconds: float


class SurgeOut(BaseModel):
    line_id: int
    line_number: str
    message: str
