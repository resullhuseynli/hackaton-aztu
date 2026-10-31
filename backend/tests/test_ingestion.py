from app.business.ingestion_service import FleetService, NetworkImportService
from app.domain.enums import Direction
from app.repository import BusRepository, NetworkRepository

from .conftest import make_source, points, source_line


def distances(network, line_id, direction=Direction.FORWARD):
    return [ls.distance_along_m for ls in network.line_stops
            if ls.line_id == line_id and ls.direction == direction]


def test_builds_lines_stops_and_ordered_distances():
    network = NetworkImportService.build_network(make_source())
    assert len(network.lines) == 3
    assert len(network.stops) == 18
    forward = distances(network, 1)
    assert forward[0] == 0
    assert forward == sorted(forward)
    assert forward[-1] > 8000  # ~8.5 km route


def test_shared_stop_is_stored_once():
    source = make_source()
    shared = dict(source["lines"][0]["stops"]["forward"][2])
    source["lines"][1]["stops"]["forward"][2] = shared
    network = NetworkImportService.build_network(source)
    assert sum(1 for s in network.stops if s.id == shared["stopId"]) == 1
    serving = {ls.line_id for ls in network.line_stops if ls.stop_id == shared["stopId"]}
    assert serving == {1, 2}


def test_reversed_shape_is_flipped():
    line = source_line(1, "1", 40.40, 100)
    line["shapes"]["forward"] = list(reversed(line["shapes"]["forward"]))  # drawn the wrong way round
    network = NetworkImportService.build_network({"lines": [line]})
    forward = distances(network, 1)
    assert forward == sorted(forward)
    assert forward[0] < 50 and forward[-1] > 8000


def test_shape_that_misses_the_stops_is_replaced_by_the_stops():
    line = source_line(1, "1", 40.40, 100)
    line["shapes"]["forward"] = [[la + 0.05, lo] for la, lo in points(40.40, 30)]  # ~5.5 km away
    network = NetworkImportService.build_network({"lines": [line]})
    shape = [(p.latitude, p.longitude) for p in network.route_points
             if p.line_id == 1 and p.direction == Direction.FORWARD]
    stops = [(s["latitude"], s["longitude"]) for s in line["stops"]["forward"]]
    assert shape == stops


def test_implausible_coordinates_are_dropped():
    line = source_line(1, "1", 40.40, 100)
    line["shapes"]["forward"].insert(5, [49.69, 40.56])  # swapped lat/lng in the middle of the shape
    line["stops"]["forward"][3]["latitude"] = 0.0        # stop without a real position
    network = NetworkImportService.build_network({"lines": [line]})
    assert all(39 < p.latitude < 42 for p in network.route_points)
    assert len(distances(network, 1)) == 5


def test_line_without_stops_is_kept_but_has_no_route():
    line = source_line(1, "1", 40.40, 100)
    line["stops"] = {"forward": [], "backward": []}
    network = NetworkImportService.build_network({"lines": [line]})
    assert [l.number for l in network.lines] == ["1"]
    assert network.line_stops == [] and network.route_points == []


def test_fleet_generation(db):
    buses = BusRepository(db).list_all()
    assert len(buses) == 12  # 8.5 km routes -> 4 buses per line
    assert len({b.bus_plate for b in buses}) == len(buses)
    assert {b.direction for b in buses} == {Direction.FORWARD, Direction.BACKWARD}
    assert all(b.passenger_limit in (80, 100, 120) for b in buses)


def test_fleet_is_reproducible(db):
    network_repo, bus_repo = NetworkRepository(db), BusRepository(db)
    first = [b.bus_plate for b in FleetService(network_repo, bus_repo, seed=7).generate()]
    second = [b.bus_plate for b in FleetService(network_repo, bus_repo, seed=7).generate()]
    assert first == second
