import pytest

from app.domain.geo import (cumulative_distances, haversine_m, interpolate, is_plausible,
                            project_onto_route)


def test_haversine_known_distance():
    # One degree of latitude is ~111.2 km everywhere.
    assert haversine_m(40.0, 49.0, 41.0, 49.0) == pytest.approx(111_195, rel=0.001)
    assert haversine_m(40.4, 49.8, 40.4, 49.8) == 0


def test_cumulative_distances_start_at_zero_and_grow():
    pts = [(40.4, 49.80), (40.4, 49.81), (40.4, 49.83)]
    dist = cumulative_distances(pts)
    assert dist[0] == 0
    assert dist[1] < dist[2]
    assert dist[2] == pytest.approx(haversine_m(40.4, 49.80, 40.4, 49.83), rel=1e-6)


def test_interpolate_ends_and_middle():
    pts = [(40.4, 49.80), (40.4, 49.82)]
    cum = cumulative_distances(pts)
    assert interpolate(pts, cum, -5) == pts[0]
    assert interpolate(pts, cum, cum[-1] + 5) == pts[-1]
    lat, lng = interpolate(pts, cum, cum[-1] / 2)
    assert lat == pytest.approx(40.4)
    assert lng == pytest.approx(49.81)


def test_project_point_next_to_straight_route():
    pts = [(40.4, 49.80), (40.4, 49.82)]
    cum = cumulative_distances(pts)
    along, offset = project_onto_route(40.4001, 49.81, pts, cum)  # ~11 m north of the middle
    assert along == pytest.approx(cum[-1] / 2, rel=0.01)
    assert offset == pytest.approx(11, abs=2)


def test_project_respects_min_distance_on_route_driving_the_same_road_twice():
    # Out along the road and back: every point of the road is passed twice.
    out = [(40.4, 49.80), (40.4, 49.81), (40.4, 49.82)]
    pts = out + out[-2::-1]
    cum = cumulative_distances(pts)
    half = cum[2]
    first, _ = project_onto_route(40.4, 49.81, pts, cum)
    second, _ = project_onto_route(40.4, 49.81, pts, cum, min_distance_m=half)
    assert first == pytest.approx(half / 2, rel=0.01)       # the way out
    assert second == pytest.approx(half * 1.5, rel=0.01)    # the way back


@pytest.mark.parametrize("lat, lng, ok", [
    (40.4, 49.8, True),
    (49.69, 40.56, False),   # latitude and longitude swapped
    (0, 0, False),
])
def test_is_plausible(lat, lng, ok):
    assert is_plausible(lat, lng) is ok
