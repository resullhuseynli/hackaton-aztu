from dataclasses import dataclass, field
from datetime import datetime

from .enums import AlertStatus, AlertType, BusStatus, DensityLevel, Direction, ReportSource


@dataclass
class Line:
    id: int
    number: str
    carrier: str | None = None
    first_point: str | None = None
    last_point: str | None = None
    route_length_km: float | None = None
    duration_minutes: int | None = None
    tariff: str | None = None
    payment_type: str | None = None
    region: str | None = None
    working_zone: str | None = None


@dataclass
class Stop:
    id: int
    code: str | None
    name: str
    address: str | None
    latitude: float | None
    longitude: float | None
    is_transport_hub: bool = False


@dataclass
class LineStop:
    line_id: int
    stop_id: int
    direction: Direction
    stop_order: int
    distance_along_m: float


@dataclass
class RoutePoint:
    line_id: int
    direction: Direction
    seq: int
    latitude: float
    longitude: float
    distance_along_m: float


@dataclass
class Bus:
    bus_id: int
    line_id: int
    bus_plate: str
    passenger_limit: int
    direction: Direction = Direction.FORWARD
    passenger_count: int = 0
    forwarding_stop_id: int | None = None
    live_latitude: float | None = None
    live_longitude: float | None = None
    position_m: float = 0.0
    speed_kmh: float = 0.0
    status: BusStatus = BusStatus.IN_SERVICE
    updated_at: datetime | None = None

    @property
    def passenger_percentage(self) -> float:
        return round(self.passenger_count * 100.0 / self.passenger_limit, 1)


@dataclass
class CrowdReport:
    line_id: int
    level: DensityLevel
    reported_at: datetime
    source: ReportSource
    stop_id: int | None = None
    bus_id: int | None = None
    id: int | None = None


@dataclass
class DensitySnapshot:
    line_id: int
    occupancy_pct: float
    report_score: float | None
    score: float
    level: DensityLevel
    active_buses: int
    computed_at: datetime


@dataclass
class Alert:
    line_id: int
    type: AlertType
    message: str
    status: AlertStatus
    created_at: datetime
    suggested_bus_count: int = 1
    suggested_donor_line_id: int | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    id: int | None = None


@dataclass
class Arrival:
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
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class Network:
    """Static transit network as imported from the source data."""
    lines: list[Line] = field(default_factory=list)
    stops: list[Stop] = field(default_factory=list)
    line_stops: list[LineStop] = field(default_factory=list)
    route_points: list[RoutePoint] = field(default_factory=list)
