import pytest

from app.business.clock import SimulationClock
from app.business.simulation_service import SimulationService
from app.domain.enums import BusStatus


@pytest.fixture
def sim(repos):
    clock = SimulationClock("08:00", speed=10)
    service = SimulationService(clock, repos.network, repos.buses, repos.reports, seed=3)
    service.start()
    return service


def run(sim, minutes, dt=10):
    for _ in range(int(minutes * 60 / dt)):
        sim.clock.advance(dt)
        sim.tick(dt)


def test_start_places_every_bus_on_its_route(repos, sim):
    buses = repos.buses.list_all()
    assert len(buses) == 12
    for bus in buses:
        assert bus.live_latitude is not None and bus.live_longitude is not None
        assert 40.39 < bus.live_latitude < 40.43


def test_buses_move_and_loads_stay_within_capacity(repos, sim):
    before = {b.bus_id: (b.direction, b.position_m) for b in repos.buses.list_all()}
    run(sim, minutes=15)
    after = repos.buses.list_all()
    assert any((b.direction, b.position_m) != before[b.bus_id] for b in after)
    for bus in after:
        assert 0 <= bus.passenger_count <= bus.passenger_limit
        assert bus.status in (BusStatus.IN_SERVICE, BusStatus.LAYOVER)
        assert bus.updated_at == sim.clock.now()


def test_record_minute_writes_telemetry_and_some_reports(repos, sim):
    for _ in range(30):
        sim.record_minute(sim.clock.now())
    with repos.buses.db.connect() as conn:
        telemetry = conn.execute("SELECT COUNT(*) FROM bus_telemetry").fetchone()[0]
        reports = conn.execute("SELECT COUNT(*) FROM crowd_reports WHERE source = 'simulated'").fetchone()[0]
    assert telemetry == 12 * 30
    assert reports > 0


def test_surge_fills_the_line(repos, sim):
    assert sim.surge(1)
    for bus in repos.buses.list_by_line(1):
        assert bus.passenger_percentage >= 92


def test_surge_unknown_line_is_rejected(sim):
    assert sim.surge(999) is False


def test_reassign_moves_buses_but_leaves_the_donor_two(repos, sim):
    moved = sim.reassign(donor_line_id=2, target_line_id=1, count=5)
    assert len(moved) == 2                 # 4 buses, two must stay
    assert len(repos.buses.list_by_line(2)) == 2
    assert len(repos.buses.list_by_line(1)) == 6
    for bus_id in moved:
        bus = repos.buses.get(bus_id)
        assert bus.line_id == 1 and bus.passenger_count == 0


def test_same_seed_gives_same_simulation(repos):
    def loads():
        clock = SimulationClock("08:00", speed=10)
        service = SimulationService(clock, repos.network, repos.buses, repos.reports, seed=5)
        service.start()
        run(service, minutes=5)
        return [(b.bus_id, b.passenger_count, round(b.position_m, 3)) for b in repos.buses.list_all()]

    assert loads() == loads()
