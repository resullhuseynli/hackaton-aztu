"""Build the database: python -m app.seed [--refresh]

--refresh  download a fresh snapshot from map.ayna.gov.az instead of using backend/sources/bus_lines.json
"""
import argparse

from app.business.ingestion_service import AynaClient, FleetService, NetworkImportService, SourceService
from app.config import settings
from app.repository import BusRepository, Database, NetworkRepository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-download data from AYNA")
    args = parser.parse_args()

    source_service = SourceService(AynaClient(settings.ayna_api), settings.source_path)
    if args.refresh or not settings.source_path.exists():
        source = source_service.download()
    else:
        source = source_service.load()

    db = Database(settings.db_path)
    db.recreate()
    network_repo = NetworkRepository(db)
    network = NetworkImportService(network_repo).import_source(source)
    buses = FleetService(network_repo, BusRepository(db), settings.random_seed).generate()

    print(f"lines: {len(network.lines)}, stops: {len(network.stops)}, line_stops: {len(network.line_stops)}, "
          f"route points: {len(network.route_points)}, buses: {len(buses)}")
    print(f"Database: {settings.db_path}")


if __name__ == "__main__":
    main()
