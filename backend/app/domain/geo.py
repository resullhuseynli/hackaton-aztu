"""Pure geometry helpers for routes expressed as (lat, lng) polylines."""
import math
from bisect import bisect_right

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def cumulative_distances(points: list[tuple[float, float]]) -> list[float]:
    distances = [0.0]
    for (lat1, lng1), (lat2, lng2) in zip(points, points[1:]):
        distances.append(distances[-1] + haversine_m(lat1, lng1, lat2, lng2))
    return distances


def _project_on_segment(lat, lng, a, b):
    """Return (fraction along a->b, distance in metres) for the closest point to (lat, lng)."""
    # Local equirectangular approximation is accurate enough within a city.
    kx = math.cos(math.radians(lat)) * 111_320.0
    ky = 110_540.0
    ax, ay = (a[1] - lng) * kx, (a[0] - lat) * ky
    bx, by = (b[1] - lng) * kx, (b[0] - lat) * ky
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    t = 0.0 if seg_len2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg_len2))
    px, py = ax + t * dx, ay + t * dy
    return t, math.hypot(px, py)


def project_onto_route(
    lat: float,
    lng: float,
    points: list[tuple[float, float]],
    cumulative: list[float],
    min_distance_m: float = 0.0,
    tolerance_m: float = 80.0,
) -> tuple[float, float]:
    """Place (lat, lng) on the route, not earlier than min_distance_m. Returns (distance along, offset).

    Takes the first pass of the route that comes within tolerance_m of the point, so stops on
    routes that drive the same road twice are matched to the right pass. Falls back to the
    closest point overall when no pass is that close.
    """
    if len(points) < 2:
        return 0.0, math.inf
    best_along, best_offset = min_distance_m, math.inf
    start = max(0, bisect_right(cumulative, min_distance_m) - 1)
    in_pass = False
    for i in range(start, len(points) - 1):
        t, offset = _project_on_segment(lat, lng, points[i], points[i + 1])
        along = cumulative[i] + t * (cumulative[i + 1] - cumulative[i])
        if along < min_distance_m:
            continue
        if offset <= tolerance_m:
            in_pass = True
        elif in_pass:
            break  # left the first close pass
        if offset < best_offset:
            best_along, best_offset = along, offset
    return best_along, best_offset


def is_plausible(lat: float, lng: float) -> bool:
    """Rough bounding box of Azerbaijan; filters swapped or zeroed coordinates."""
    return 38.0 < lat < 42.5 and 44.5 < lng < 51.0


def interpolate(points: list[tuple[float, float]], cumulative: list[float], distance_m: float) -> tuple[float, float]:
    if not points:
        raise ValueError("empty route")
    if distance_m <= 0 or len(points) == 1:
        return points[0]
    if distance_m >= cumulative[-1]:
        return points[-1]
    i = bisect_right(cumulative, distance_m) - 1
    seg = cumulative[i + 1] - cumulative[i]
    t = 0.0 if seg == 0 else (distance_m - cumulative[i]) / seg
    (lat1, lng1), (lat2, lng2) = points[i], points[i + 1]
    return lat1 + (lat2 - lat1) * t, lng1 + (lng2 - lng1) * t
