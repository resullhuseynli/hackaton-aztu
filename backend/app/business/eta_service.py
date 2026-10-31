"""Estimated arrival times from live bus positions along the route geometry."""
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta

from app.domain import rules
from app.domain.enums import Direction
from app.domain.models import Arrival, Bus, LineStop
from app.repository import BusRepository, NetworkRepository

SPEED_WINDOW = timedelta(minutes=5)


class EtaService:
    def __init__(self, network_repo: NetworkRepository, bus_repo: BusRepository):
        self.network_repo = network_repo
        self.bus_repo = bus_repo
        self._line_stops: dict[tuple[int, Direction], list[LineStop]] | None = None

    def _stops(self, line_id: int, direction: Direction) -> list[LineStop]:
        if self._line_stops is None:
            self._line_stops = self.network_repo.all_line_stops()  # static, cache once
        return self._line_stops.get((line_id, direction), [])

    def _speeds(self, now: datetime) -> dict[int, float]:
        return self.bus_repo.average_speed_kmh(now - SPEED_WINDOW)

    def eta_to(self, bus: Bus, target: LineStop, speeds: dict[int, float]) -> tuple[int, float, int] | None:
        """(eta seconds, distance m, stops in between) for a bus on the same line and direction, or None if passed."""
        if bus.line_id != target.line_id or bus.direction != target.direction:
            return None
        distance = target.distance_along_m - bus.position_m
        if distance < -1:
            return None
        distances = [ls.distance_along_m for ls in self._stops(bus.line_id, bus.direction)]
        between = max(0, bisect_left(distances, target.distance_along_m) - bisect_right(distances, bus.position_m))
        speed = speeds.get(bus.bus_id) or bus.speed_kmh or rules.DEFAULT_SPEED_KMH
        return rules.eta_seconds(max(distance, 0.0), speed, between), max(distance, 0.0), between

    def arrivals_at_stop(self, stop_id: int, now: datetime, limit: int = 15) -> list[Arrival]:
        targets = self.network_repo.line_stops_for_stop(stop_id)
        speeds = self._speeds(now)
        arrivals: list[Arrival] = []
        lines = {}
        for target in targets:
            line = lines.setdefault(target.line_id, self.network_repo.get_line(target.line_id))
            for bus in self.bus_repo.list_by_line(target.line_id):
                estimate = self.eta_to(bus, target, speeds)
                if estimate is None:
                    continue
                eta, distance, between = estimate
                arrivals.append(Arrival(
                    bus_id=bus.bus_id, bus_plate=bus.bus_plate, line_id=line.id, line_number=line.number,
                    direction=bus.direction, eta_seconds=eta, distance_m=round(distance), stops_away=between,
                    passenger_percentage=bus.passenger_percentage,
                    density_level=rules.density_level(bus.passenger_percentage),
                    latitude=bus.live_latitude, longitude=bus.live_longitude,
                ))
        arrivals.sort(key=lambda a: a.eta_seconds)
        return arrivals[:limit]

    def next_stop_eta(self, buses: list[Bus], now: datetime) -> dict[int, int]:
        """ETA in seconds of each bus to its next stop."""
        speeds = self._speeds(now)
        result = {}
        for bus in buses:
            target = next((ls for ls in self._stops(bus.line_id, bus.direction)
                           if ls.stop_id == bus.forwarding_stop_id and ls.distance_along_m >= bus.position_m - 1), None)
            estimate = self.eta_to(bus, target, speeds) if target else None
            if estimate:
                result[bus.bus_id] = estimate[0]
        return result
