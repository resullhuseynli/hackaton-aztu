"""Importing the static network from map.ayna.gov.az and generating the (fake) fleet."""
import json
import random
import string
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.domain.enums import Direction
from app.domain.geo import cumulative_distances, haversine_m, is_plausible, project_onto_route
from app.domain.models import Bus, Line, LineStop, Network, RoutePoint, Stop
from app.repository import BusRepository, NetworkRepository

AYNA_DIRECTIONS = {1: Direction.FORWARD, 2: Direction.BACKWARD}
# A stop further than this from the road shape counts as a miss; too many misses and the shape is discarded.
MAX_STOP_OFFSET_M = 150.0
MAX_MISSED_STOP_SHARE = 0.1
BAKU_PLATE_REGIONS = ("10", "77", "90", "99")
BUS_CAPACITIES = (80, 100, 120)


class AynaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def _get(self, path: str, retries: int = 3):
        for attempt in range(retries):
            try:
                req = urllib.request.Request(f"{self.base_url}{path}", headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.load(resp)
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)

    def bus_list(self) -> list[dict]:
        return self._get("/bus/getBusList")

    def bus_detail(self, bus_id: int) -> dict:
        return self._get(f"/bus/getBusById?id={bus_id}")


def _to_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number or None  # the API uses 0 for "unknown"


class SourceService:
    """Downloads the AYNA data and stores it as a JSON snapshot under backend/sources."""

    def __init__(self, client: AynaClient, source_path: Path):
        self.client = client
        self.source_path = source_path

    def download(self) -> dict:
        buses = self.client.bus_list()
        print(f"AYNA: {len(buses)} lines")
        failed = []

        def fetch(bus):
            try:
                return self._to_source_line(self.client.bus_detail(bus["id"]))
            except Exception as exc:
                print(f"  line {bus['number']} (id={bus['id']}) failed: {exc}")
                failed.append({"id": bus["id"], "number": bus["number"], "error": str(exc)})
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            lines = [line for line in pool.map(fetch, buses) if line]
        data = {
            "source": "https://map.ayna.gov.az/",
            "scrapedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "lineCount": len(lines),
            "lines": lines,
            "failedLines": failed,
        }
        self.source_path.parent.mkdir(parents=True, exist_ok=True)
        self.source_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return data

    def load(self) -> dict:
        return json.loads(self.source_path.read_text(encoding="utf-8"))

    @staticmethod
    def _to_source_line(bus: dict) -> dict:
        stops = {d.value: [] for d in AYNA_DIRECTIONS.values()}
        for item in bus.get("stops") or []:
            direction = AYNA_DIRECTIONS.get(item.get("directionTypeId"))
            if not direction:
                continue
            stop = item.get("stop") or {}
            stops[direction.value].append({
                "stopId": item.get("stopId"),
                "code": item.get("stopCode") or stop.get("code"),
                "name": item.get("stopName") or stop.get("name"),
                # The API has no separate address field; the stop name is the street/landmark label.
                "address": stop.get("name") or item.get("stopName"),
                "latitude": _to_float(stop.get("latitude")),
                "longitude": _to_float(stop.get("longitude")),
                "isTransportHub": bool(stop.get("isTransportHub")),
            })
        shapes = {d.value: [] for d in AYNA_DIRECTIONS.values()}
        for route in bus.get("routes") or []:
            direction = AYNA_DIRECTIONS.get(route.get("directionTypeId"))
            coords = [[p["lat"], p["lng"]] for p in route.get("flowCoordinates") or []]
            # Some lines have several variants per direction; keep the most detailed one.
            if direction and len(coords) > len(shapes[direction.value]):
                shapes[direction.value] = coords
        return {
            "id": bus["id"],
            "number": bus["number"],
            "carrier": bus.get("carrier"),
            "firstPoint": bus.get("firstPoint"),
            "lastPoint": bus.get("lastPoint"),
            "routeLengthKm": bus.get("routLength"),
            "durationMinutes": bus.get("durationMinuts"),
            "tariff": bus.get("tariffStr") or (str(bus["tariff"]) if bus.get("tariff") is not None else None),
            "paymentType": (bus.get("paymentType") or {}).get("name"),
            "region": (bus.get("region") or {}).get("name"),
            "workingZone": (bus.get("workingZoneType") or {}).get("name"),
            "stops": stops,
            "shapes": shapes,
        }


class NetworkImportService:
    """Turns the JSON snapshot into the relational network, placing every stop on its route geometry."""

    def __init__(self, network_repo: NetworkRepository):
        self.network_repo = network_repo

    def import_source(self, source: dict) -> Network:
        network = self.build_network(source)
        self.network_repo.replace(network)
        return network

    @staticmethod
    def build_network(source: dict) -> Network:
        network = Network()
        stops: dict[int, Stop] = {}
        for raw in source["lines"]:
            line_id = raw["id"]
            network.lines.append(Line(
                id=line_id, number=raw["number"], carrier=raw["carrier"], first_point=raw["firstPoint"],
                last_point=raw["lastPoint"], route_length_km=raw["routeLengthKm"],
                duration_minutes=raw["durationMinutes"], tariff=raw["tariff"], payment_type=raw["paymentType"],
                region=raw["region"], working_zone=raw["workingZone"],
            ))
            for direction in Direction:
                raw_stops = raw["stops"].get(direction.value) or []
                located = [s for s in raw_stops
                           if s["latitude"] and s["longitude"] and is_plausible(s["latitude"], s["longitude"])]
                if len(located) < 2:
                    continue  # nothing a bus could drive along
                stop_coords = [(s["latitude"], s["longitude"]) for s in located]
                shape = [tuple(p) for p in raw["shapes"].get(direction.value) or [] if is_plausible(*p)]
                shape, distances = NetworkImportService._match_stops(stop_coords, shape)
                cumulative = cumulative_distances(shape)
                network.route_points += [
                    RoutePoint(line_id, direction, seq, lat, lng, round(dist, 1))
                    for seq, ((lat, lng), dist) in enumerate(zip(shape, cumulative))
                ]
                for order, (s, along) in enumerate(zip(located, distances), start=1):
                    stops.setdefault(s["stopId"], Stop(
                        id=s["stopId"], code=s["code"], name=s["name"], address=s["address"],
                        latitude=s["latitude"], longitude=s["longitude"], is_transport_hub=s["isTransportHub"],
                    ))
                    network.line_stops.append(LineStop(line_id, s["stopId"], direction, order, round(along, 1)))
        network.stops = list(stops.values())
        return network

    @staticmethod
    def _match_stops(
        stop_coords: list[tuple[float, float]], shape: list[tuple[float, float]]
    ) -> tuple[list[tuple[float, float]], list[float]]:
        """Return the route geometry to use and each stop's distance along it.

        AYNA shapes are sometimes drawn in the opposite direction to the stop order, and some
        don't follow the stops at all. Reversed shapes are flipped; shapes that still miss the
        stops are replaced by a polyline through the stops themselves.
        """
        if len(shape) >= 2:
            first, last = stop_coords[0], stop_coords[-1]
            forward_gap = haversine_m(*first, *shape[0]) + haversine_m(*last, *shape[-1])
            reverse_gap = haversine_m(*first, *shape[-1]) + haversine_m(*last, *shape[0])
            if reverse_gap < forward_gap:
                shape = shape[::-1]
            cumulative = cumulative_distances(shape)
            distances, misses, along = [], 0, 0.0
            for lat, lng in stop_coords:
                along, offset = project_onto_route(lat, lng, shape, cumulative, along)
                distances.append(along)
                misses += offset > MAX_STOP_OFFSET_M
            if misses <= len(stop_coords) * MAX_MISSED_STOP_SHARE:
                return shape, distances
        return stop_coords, cumulative_distances(stop_coords)


class FleetService:
    """Generates a fake fleet: a few buses per line, sized by route length."""

    def __init__(self, network_repo: NetworkRepository, bus_repo: BusRepository, seed: int):
        self.network_repo = network_repo
        self.bus_repo = bus_repo
        self.rng = random.Random(seed)

    def generate(self) -> list[Bus]:
        buses: list[Bus] = []
        plates: set[str] = set()
        for line_id in self.network_repo.line_ids_with_routes():
            line = self.network_repo.get_line(line_id)
            count = max(3, min(10, round((line.route_length_km or 10) / 4) + 2))
            for i in range(count):
                buses.append(Bus(
                    bus_id=len(buses) + 1,
                    line_id=line_id,
                    bus_plate=self._plate(plates),
                    passenger_limit=self.rng.choice(BUS_CAPACITIES),
                    direction=Direction.FORWARD if i % 2 == 0 else Direction.BACKWARD,
                ))
        self.bus_repo.replace_fleet(buses)
        return buses

    def _plate(self, taken: set[str]) -> str:
        while True:
            plate = "{}-{}{}-{:03d}".format(
                self.rng.choice(BAKU_PLATE_REGIONS),
                self.rng.choice(string.ascii_uppercase), self.rng.choice(string.ascii_uppercase),
                self.rng.randint(1, 999),
            )
            if plate not in taken:
                taken.add(plate)
                return plate
