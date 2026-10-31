"""Fake real-time feed: moves the fleet along the real AYNA routes and produces passenger reports.

It stands in for the GPS trackers, passenger counters and passenger app of a real deployment:
everything it produces goes through the same repositories the real feeds would use.

Passenger model: people arrive at each stop at a steady rate and wait until a bus with room
comes by, so more buses on a line means shorter headways and fewer passengers per bus.
"""
import math
import random
import threading
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from app.domain import rules
from app.domain.enums import BusStatus, DensityLevel, Direction, ReportSource
from app.domain.geo import interpolate
from app.domain.models import Bus, CrowdReport, LineStop
from app.repository import BusRepository, NetworkRepository, ReportRepository

from .clock import SimulationClock

CRUISE_SPEED_KMH = 26.0
PEAK_SPEED_KMH = 15.0
PEAK_DEMAND = 1.6
OFFPEAK_DEMAND = 0.7
NIGHT_DEMAND = 0.2

ALIGHT_SHARE = 0.15            # share of riders leaving at each intermediate stop
BOARDING_SECONDS = 2.0         # dwell time per boarding or alighting passenger
MIN_DWELL_SECONDS = 15.0
MAX_DWELL_SECONDS = 60.0
LAYOVER_SECONDS = 180.0        # break at the terminal before driving back
MAX_WAITING_PER_STOP = 150
ABANDON_SECONDS = 1200.0       # average time a passenger waits before giving up

# Calibration: at normal demand a bus picks up ~10% of an average bus per stop visit
# (before passengers who gave up are taken into account).
AVERAGE_CAPACITY = 100
BOARDING_SHARE_PER_VISIT = 0.10
PLANNING_SPEED_KMH = 20.0

HOT_LINE_SHARE = 0.08
COLD_LINE_SHARE = 0.15
HOT_DEMAND = 2.1
COLD_DEMAND = 0.35

REPORT_PROBABILITY_PER_MINUTE = 0.02  # chance that someone on a given bus reports in a minute
REPORT_NOISE = 0.2                    # share of reports that are plain wrong

SURGE_DEMAND = 3.0
SURGE_MIN_DEMAND = 8.0
SURGE_DURATION = timedelta(minutes=30)


@dataclass
class Geometry:
    points: list[tuple[float, float]]
    cumulative: list[float]
    stops: list[LineStop]

    @property
    def length(self) -> float:
        return self.cumulative[-1]


@dataclass
class LineProfile:
    demand: float               # 1.0 normal, >1 overcrowded line, <1 underused line
    traffic: float              # speed multiplier for this corridor
    arrival_rate: float         # passengers per second per stop at demand 1.0


@dataclass
class BusRuntime:
    bus: Bus
    next_stop: int
    speed_factor: float
    dwell_left: float = 0.0


class SimulationService:
    def __init__(self, clock: SimulationClock, network_repo: NetworkRepository, bus_repo: BusRepository,
                 report_repo: ReportRepository, seed: int):
        self.clock = clock
        self.network_repo = network_repo
        self.bus_repo = bus_repo
        self.report_repo = report_repo
        self.rng = random.Random(seed)
        self._lock = threading.RLock()
        self.geometries: dict[tuple[int, Direction], Geometry] = {}
        self.profiles: dict[int, LineProfile] = {}
        self.runtimes: list[BusRuntime] = []
        self.surge_until: dict[int, datetime] = {}
        self._waiting: dict[tuple[int, Direction, int], float] = {}
        self._last_visit: dict[tuple[int, Direction, int], datetime] = {}

    # ---- setup -------------------------------------------------------------------------------

    def start(self) -> None:
        routes = self.network_repo.all_routes()
        for key, stops in self.network_repo.all_line_stops().items():
            points = routes.get(key)
            if not points or len(points) < 2:
                continue
            self.geometries[key] = Geometry(
                points=[(p.latitude, p.longitude) for p in points],
                cumulative=[p.distance_along_m for p in points],
                stops=stops,
            )
        buses = [b for b in self.bus_repo.list_all() if self._has_geometry(b.line_id)]
        self._build_profiles(buses)
        now = self.clock.now()
        by_line_direction: dict[tuple[int, Direction], list[Bus]] = {}
        for bus in buses:
            if (bus.line_id, bus.direction) not in self.geometries:
                bus.direction = bus.direction.opposite
            by_line_direction.setdefault((bus.line_id, bus.direction), []).append(bus)
        for (line_id, direction), group in by_line_direction.items():
            geometry = self.geometries[(line_id, direction)]
            for k, bus in enumerate(group):
                position = geometry.length * (k + self.rng.random() * 0.5) / len(group)
                runtime = BusRuntime(bus, self._next_stop_index(geometry, position), self.rng.uniform(0.85, 1.15))
                bus.position_m = position
                load = min(0.95, self.profiles[line_id].demand * self._time_demand(now) * 0.45)
                bus.passenger_count = int(bus.passenger_limit * load * self.rng.uniform(0.5, 1.1))
                self._place(runtime, now)
                self.runtimes.append(runtime)
        self.bus_repo.save_live_state([r.bus for r in self.runtimes])

    def _has_geometry(self, line_id: int) -> bool:
        return any((line_id, d) in self.geometries for d in Direction)

    def _build_profiles(self, buses: list[Bus]) -> None:
        fleet_size: dict[int, int] = {}
        for bus in buses:
            fleet_size[bus.line_id] = fleet_size.get(bus.line_id, 0) + 1
        line_ids = sorted(fleet_size)
        shuffled = line_ids[:]
        self.rng.shuffle(shuffled)
        hot = set(shuffled[:round(len(shuffled) * HOT_LINE_SHARE)])
        cold = set(shuffled[len(hot):len(hot) + round(len(shuffled) * COLD_LINE_SHARE)])
        for line_id in line_ids:
            if line_id in hot:
                demand = HOT_DEMAND * self.rng.uniform(0.9, 1.1)
            elif line_id in cold:
                demand = COLD_DEMAND * self.rng.uniform(0.8, 1.2)
            else:
                demand = self.rng.uniform(0.8, 1.2)
            self.profiles[line_id] = LineProfile(
                demand=demand,
                traffic=self.rng.uniform(0.8, 1.15),
                arrival_rate=AVERAGE_CAPACITY * BOARDING_SHARE_PER_VISIT / self._planned_headway(line_id, fleet_size[line_id]),
            )

    def _planned_headway(self, line_id: int, buses: int) -> float:
        """Seconds between buses at a stop if the fleet were evenly spread."""
        cycle = 0.0
        for direction in Direction:
            geometry = self.geometries.get((line_id, direction))
            if geometry:
                cycle += geometry.length / (PLANNING_SPEED_KMH / 3.6) + len(geometry.stops) * 30 + LAYOVER_SECONDS
        return max(cycle / max(buses, 1), 120.0)

    # ---- simulation step ---------------------------------------------------------------------

    def tick(self, dt: float) -> None:
        with self._lock:
            now = self.clock.now()
            speed_base = PEAK_SPEED_KMH if rules.is_peak_hour(now) else CRUISE_SPEED_KMH
            for runtime in self.runtimes:
                self._move(runtime, dt, speed_base, now)
                self._place(runtime, now)
            self.bus_repo.save_live_state([r.bus for r in self.runtimes])

    def _move(self, runtime: BusRuntime, dt: float, speed_base: float, now: datetime) -> None:
        bus = runtime.bus
        speed_kmh = speed_base * self.profiles[bus.line_id].traffic * runtime.speed_factor
        speed = speed_kmh / 3.6
        remaining = dt
        moved = False
        for _ in range(20):  # a bus can pass several closely spaced stops in one tick
            if runtime.dwell_left > 0:
                used = min(runtime.dwell_left, remaining)
                runtime.dwell_left -= used
                remaining -= used
            if remaining <= 0:
                break
            geometry = self.geometries[(bus.line_id, bus.direction)]
            at_terminal = runtime.next_stop >= len(geometry.stops)
            target = geometry.length if at_terminal else geometry.stops[runtime.next_stop].distance_along_m
            needed = max(target - bus.position_m, 0.0) / speed
            if needed > remaining:
                bus.position_m += speed * remaining
                moved = True
                break
            bus.position_m = target
            remaining -= needed
            moved = moved or needed > 0
            if at_terminal:
                self._turn_around(runtime)
            else:
                self._serve_stop(runtime, now)
                runtime.next_stop += 1
        bus.speed_kmh = round(speed_kmh, 1) if moved and runtime.dwell_left <= 0 else 0.0
        if self.rng.random() < 0.01:
            runtime.speed_factor = self.rng.uniform(0.85, 1.15)

    def _serve_stop(self, runtime: BusRuntime, now: datetime) -> None:
        bus = runtime.bus
        geometry = self.geometries[(bus.line_id, bus.direction)]
        is_last = runtime.next_stop == len(geometry.stops) - 1
        if is_last:
            alighting = bus.passenger_count
        else:
            alighting = min(bus.passenger_count, round(bus.passenger_count * ALIGHT_SHARE * self.rng.uniform(0.5, 1.5)))
        bus.passenger_count -= alighting
        boarding = 0
        if not is_last:
            key = (bus.line_id, bus.direction, runtime.next_stop)
            waiting = self._accrue_waiting(key, now)
            boarding = min(int(waiting), bus.passenger_limit - bus.passenger_count)
            self._waiting[key] = waiting - boarding
            bus.passenger_count += boarding
        runtime.dwell_left = min(MAX_DWELL_SECONDS, MIN_DWELL_SECONDS + (boarding + alighting) * BOARDING_SECONDS)

    def _accrue_waiting(self, key: tuple[int, Direction, int], now: datetime) -> float:
        line_id = key[0]
        profile = self.profiles[line_id]
        last = self._last_visit.get(key)
        if last is None:
            # Pretend the previous bus came by a random part of a planned headway ago.
            planned_headway = AVERAGE_CAPACITY * BOARDING_SHARE_PER_VISIT / profile.arrival_rate
            elapsed = planned_headway * self.rng.uniform(0.3, 1.0)
        else:
            elapsed = (now - last).total_seconds()
        self._last_visit[key] = now
        # People arrive at a steady rate and give up (taxi, walking) after ABANDON_SECONDS on average,
        # so the queue saturates instead of growing forever.
        kept = math.exp(-elapsed / ABANDON_SECONDS)
        arrivals = profile.arrival_rate * self._demand(line_id, now) * ABANDON_SECONDS * (1 - kept)
        return min(self._waiting.get(key, 0.0) * kept + arrivals, MAX_WAITING_PER_STOP)

    def _turn_around(self, runtime: BusRuntime) -> None:
        bus = runtime.bus
        bus.passenger_count = 0
        if (bus.line_id, bus.direction.opposite) in self.geometries:
            bus.direction = bus.direction.opposite
        bus.position_m = 0.0
        runtime.next_stop = 0
        runtime.dwell_left = LAYOVER_SECONDS

    def _place(self, runtime: BusRuntime, now: datetime) -> None:
        bus = runtime.bus
        geometry = self.geometries[(bus.line_id, bus.direction)]
        bus.live_latitude, bus.live_longitude = interpolate(geometry.points, geometry.cumulative, bus.position_m)
        bus.forwarding_stop_id = (geometry.stops[runtime.next_stop].stop_id
                                  if runtime.next_stop < len(geometry.stops) else None)
        # Out of service: driving empty from the last stop to the terminal, or waiting there
        # (at the first stop, index 0) until the layover is over.
        past_last_stop = runtime.next_stop >= len(geometry.stops)
        on_layover = past_last_stop or (runtime.next_stop == 0 and runtime.dwell_left > 0)
        bus.status = BusStatus.LAYOVER if on_layover else BusStatus.IN_SERVICE
        bus.updated_at = now

    @staticmethod
    def _next_stop_index(geometry: Geometry, position: float) -> int:
        for i, stop in enumerate(geometry.stops):
            if stop.distance_along_m >= position:
                return i
        return len(geometry.stops)

    def _time_demand(self, moment: datetime) -> float:
        if rules.is_peak_hour(moment):
            return PEAK_DEMAND
        if moment.time() < time(6, 0):
            return NIGHT_DEMAND
        return OFFPEAK_DEMAND

    def _demand(self, line_id: int, moment: datetime) -> float:
        demand = self.profiles[line_id].demand * self._time_demand(moment)
        if self.surge_until.get(line_id, moment) > moment:
            # Even an underused line must stay overcrowded for the whole surge.
            demand = max(demand * SURGE_DEMAND, SURGE_MIN_DEMAND)
        return demand

    # ---- once per simulated minute -----------------------------------------------------------

    def record_minute(self, now: datetime) -> None:
        with self._lock:
            buses = [r.bus for r in self.runtimes]
            self.bus_repo.record_telemetry(buses, now)
            reports = []
            for bus in buses:
                if self.rng.random() >= REPORT_PROBABILITY_PER_MINUTE:
                    continue
                level = rules.density_level(bus.passenger_percentage)
                if self.rng.random() < REPORT_NOISE:
                    level = self.rng.choice(list(DensityLevel))
                reports.append(CrowdReport(line_id=bus.line_id, level=level, reported_at=now,
                                           source=ReportSource.SIMULATED, stop_id=bus.forwarding_stop_id,
                                           bus_id=bus.bus_id))
            self.report_repo.add_many(reports)

    # ---- operator / demo actions -------------------------------------------------------------

    def surge(self, line_id: int) -> bool:
        """Demo: make a line suddenly overcrowded for SURGE_DURATION."""
        with self._lock:
            if line_id not in self.profiles:
                return False
            now = self.clock.now()
            self.surge_until[line_id] = now + SURGE_DURATION
            for runtime in self.runtimes:
                bus = runtime.bus
                if bus.line_id == line_id:
                    bus.passenger_count = max(bus.passenger_count, int(bus.passenger_limit * self.rng.uniform(0.92, 1.0)))
            for key in list(self._last_visit):
                if key[0] == line_id:
                    self._waiting[key] = max(self._waiting.get(key, 0.0), 40.0)
            self.bus_repo.save_live_state([r.bus for r in self.runtimes if r.bus.line_id == line_id])
            return True

    def reassign(self, donor_line_id: int, target_line_id: int, count: int) -> list[int]:
        """Move up to `count` of the emptiest buses from the donor line onto the target line."""
        with self._lock:
            if target_line_id not in self.profiles:
                return []
            donors = sorted((r for r in self.runtimes if r.bus.line_id == donor_line_id),
                            key=lambda r: r.bus.passenger_count)
            movable = donors[:max(0, min(count, len(donors) - 2))]  # leave the donor line at least two buses
            directions = [d for d in Direction if (target_line_id, d) in self.geometries]
            now = self.clock.now()
            for i, runtime in enumerate(movable):
                bus = runtime.bus
                bus.line_id = target_line_id
                bus.direction = directions[i % len(directions)]
                geometry = self.geometries[(target_line_id, bus.direction)]
                bus.position_m = geometry.length * (i // len(directions) + 0.5) / max(1, len(movable))
                bus.passenger_count = 0
                runtime.next_stop = self._next_stop_index(geometry, bus.position_m)
                runtime.dwell_left = 0.0
                self._place(runtime, now)
            self.bus_repo.save_live_state([r.bus for r in movable])
            return [r.bus.bus_id for r in movable]
