"""Wires repositories, services and the engine together."""
from datetime import timedelta

from app.business.analytics_service import AnalyticsService
from app.business.clock import SimulationClock
from app.business.engine import TransitEngine
from app.business.eta_service import EtaService
from app.business.operator_service import OperatorService
from app.business.passenger_service import PassengerService
from app.business.simulation_service import SimulationService
from app.config import Settings
from app.repository import (AlertRepository, BusRepository, Database, DensityRepository, MaintenanceRepository,
                            NetworkRepository, ReportRepository)


class Container:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.db_path)
        network = NetworkRepository(self.db)
        buses = BusRepository(self.db)
        reports = ReportRepository(self.db)
        density = DensityRepository(self.db)
        alerts = AlertRepository(self.db)
        self.network_repo = network

        report_window = timedelta(minutes=settings.report_window_minutes)
        self.clock = SimulationClock(settings.sim_start, settings.sim_speed)
        self.simulation = SimulationService(self.clock, network, buses, reports, settings.random_seed)
        self.analytics = AnalyticsService(
            network, buses, reports, density, alerts,
            alert_window=timedelta(minutes=settings.alert_window_minutes),
            resolve_window=timedelta(minutes=settings.resolve_window_minutes),
            report_window=report_window,
        )
        self.engine = TransitEngine(
            self.clock, self.simulation, self.analytics, MaintenanceRepository(self.db),
            tick_seconds=settings.tick_seconds,
            retention=timedelta(minutes=settings.history_retention_minutes),
        )
        self.eta = EtaService(network, buses)
        self.passenger = PassengerService(self.clock, network, buses, reports, density, self.eta)
        self.operator = OperatorService(self.clock, network, buses, reports, density, alerts, self.simulation,
                                        report_window)
