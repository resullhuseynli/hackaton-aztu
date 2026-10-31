import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: Path = BACKEND_DIR / "database" / "transport.db"
    source_path: Path = BACKEND_DIR / "sources" / "bus_lines.json"
    ayna_api: str = "https://map-api.ayna.gov.az/api"

    # Simulation: one real tick advances the simulated clock by tick_seconds * sim_speed.
    sim_speed: float = field(default_factory=lambda: float(os.getenv("SIM_SPEED", "10")))
    sim_start: str = field(default_factory=lambda: os.getenv("SIM_START", "08:00"))
    tick_seconds: float = field(default_factory=lambda: float(os.getenv("TICK_SECONDS", "1")))
    random_seed: int = field(default_factory=lambda: int(os.getenv("SIM_SEED", "42")))

    # Analytics
    alert_window_minutes: int = 10
    resolve_window_minutes: int = 5
    report_window_minutes: int = 10
    history_retention_minutes: int = 180

    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")


settings = Settings()
