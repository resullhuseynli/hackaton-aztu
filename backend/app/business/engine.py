"""Drives the system: advances the simulated clock, the fake feed and the analytics schedule."""
import asyncio
import logging
from datetime import datetime, timedelta

from app.repository import MaintenanceRepository

from .analytics_service import AnalyticsService
from .clock import SimulationClock
from .simulation_service import SimulationService

log = logging.getLogger(__name__)
PRUNE_EVERY_MINUTES = 10


class TransitEngine:
    def __init__(self, clock: SimulationClock, simulation: SimulationService, analytics: AnalyticsService,
                 maintenance: MaintenanceRepository, tick_seconds: float, retention: timedelta):
        self.clock = clock
        self.simulation = simulation
        self.analytics = analytics
        self.maintenance = maintenance
        self.tick_seconds = tick_seconds
        self.retention = retention
        self._last_minute: datetime | None = None
        self._minutes = 0

    def start(self) -> None:
        self.maintenance.clear_live_data()  # history from a previous run has timestamps from another clock
        self.simulation.start()
        self._on_minute(self.clock.now().replace(second=0, microsecond=0))

    def step(self, sim_seconds: float | None = None) -> None:
        """Advance the simulation by sim_seconds (default: one real tick at the clock's speed)."""
        dt = sim_seconds if sim_seconds is not None else self.tick_seconds * self.clock.speed
        now = self.clock.advance(dt)
        self.simulation.tick(dt)
        minute = now.replace(second=0, microsecond=0)
        if minute != self._last_minute:
            self._on_minute(minute)

    def _on_minute(self, minute: datetime) -> None:
        self._last_minute = minute
        self._minutes += 1
        self.simulation.record_minute(minute)
        for alert in self.analytics.run(minute):
            log.info("ALERT %s", alert.message)
        if self._minutes % PRUNE_EVERY_MINUTES == 0:
            self.maintenance.prune(minute - self.retention)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time() + self.tick_seconds
        while True:
            await asyncio.sleep(max(0.0, next_tick - loop.time()))
            next_tick += self.tick_seconds
            try:
                await asyncio.to_thread(self.step)
            except Exception:
                log.exception("engine step failed")
