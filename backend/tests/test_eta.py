from datetime import timedelta

import pytest

from app.business.eta_service import EtaService
from app.domain import rules
from app.domain.enums import Direction

from .conftest import START

TARGET_STOP = 103  # 4th stop of line 1 (forward)


@pytest.fixture
def eta(repos):
    return EtaService(repos.network, repos.buses)


@pytest.fixture
def forward_stops(repos):
    return repos.network.all_line_stops()[(1, Direction.FORWARD)]


def place_bus(repos, position_m, speed_kmh=36.0, direction=Direction.FORWARD):
    bus = repos.buses.list_by_line(1)[0]
    bus.direction, bus.position_m, bus.speed_kmh = direction, position_m, speed_kmh
    repos.buses.save_live_state([bus])
    return bus


def arrival_of(eta, bus_id):
    return next((a for a in eta.arrivals_at_stop(TARGET_STOP, START) if a.bus_id == bus_id), None)


def test_eta_counts_distance_speed_and_intermediate_stops(repos, eta, forward_stops):
    bus = place_bus(repos, position_m=100)
    target = next(ls for ls in forward_stops if ls.stop_id == TARGET_STOP)
    arrival = arrival_of(eta, bus.bus_id)
    # Stops 2 and 3 lie between the bus and stop 4.
    assert arrival.stops_away == 2
    assert arrival.distance_m == pytest.approx(target.distance_along_m - 100, abs=1)
    assert arrival.eta_seconds == rules.eta_seconds(target.distance_along_m - 100, 36, 2)
    assert arrival.line_number == "1"


def test_bus_that_passed_the_stop_is_not_listed(repos, eta, forward_stops):
    target = next(ls for ls in forward_stops if ls.stop_id == TARGET_STOP)
    bus = place_bus(repos, position_m=target.distance_along_m + 200)
    assert arrival_of(eta, bus.bus_id) is None


def test_bus_in_other_direction_is_not_matched(repos, eta, forward_stops):
    bus = place_bus(repos, position_m=0, direction=Direction.BACKWARD)
    target = next(ls for ls in forward_stops if ls.stop_id == TARGET_STOP)
    assert eta.eta_to(bus, target, speeds={}) is None


def test_recent_average_speed_is_preferred(repos, eta, forward_stops):
    bus = place_bus(repos, position_m=100, speed_kmh=36)
    bus.speed_kmh = 18
    repos.buses.record_telemetry([bus], START - timedelta(minutes=1))
    target = next(ls for ls in forward_stops if ls.stop_id == TARGET_STOP)
    arrival = arrival_of(eta, bus.bus_id)
    assert arrival.eta_seconds == rules.eta_seconds(target.distance_along_m - 100, 18, 2)


def test_arrivals_are_sorted_by_eta(repos, eta):
    arrivals = eta.arrivals_at_stop(TARGET_STOP, START)
    assert arrivals == sorted(arrivals, key=lambda a: a.eta_seconds)
