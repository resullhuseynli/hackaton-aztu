import threading
from datetime import datetime, time, timedelta


class SimulationClock:
    """Simulated wall clock. Every timestamp in the system comes from here."""

    def __init__(self, start: str, speed: float):
        hour, minute = (int(part) for part in start.split(":"))
        self._now = datetime.combine(datetime.now().date(), time(hour, minute))
        self.speed = speed
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> datetime:
        with self._lock:
            self._now += timedelta(seconds=seconds)
            return self._now
