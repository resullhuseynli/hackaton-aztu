"""Business rules of the transit domain. Pure functions, no I/O."""
import math
from datetime import datetime, time, timedelta

from .enums import DensityLevel

# Density score is 0..100. A line is "high" above 85 and "low" below 50.
HIGH_THRESHOLD = 85.0
LOW_THRESHOLD = 50.0

# Maximum share of the line density score that comes from passenger reports.
REPORT_WEIGHT = 0.3
REPORTS_FOR_FULL_WEIGHT = 5

# Score a passenger report represents.
REPORT_LEVEL_SCORE = {
    DensityLevel.LOW: 25.0,
    DensityLevel.MEDIUM: 65.0,
    DensityLevel.HIGH: 95.0,
}

PEAK_PERIODS = ((time(7, 30), time(9, 30)), (time(17, 30), time(19, 30)))

STOP_DWELL_SECONDS = 30
DEFAULT_SPEED_KMH = 20.0
MIN_SPEED_KMH = 5.0


def density_level(score: float) -> DensityLevel:
    if score > HIGH_THRESHOLD:
        return DensityLevel.HIGH
    if score >= LOW_THRESHOLD:
        return DensityLevel.MEDIUM
    return DensityLevel.LOW


def report_score(levels: list[DensityLevel]) -> float | None:
    if not levels:
        return None
    return sum(REPORT_LEVEL_SCORE[level] for level in levels) / len(levels)


def density_score(occupancy_pct: float, reports_score: float | None, report_count: int = 0) -> float:
    """Blend measured occupancy with crowdsourced reports.

    Reports get their full weight only once there are REPORTS_FOR_FULL_WEIGHT of them, so one or two
    (possibly wrong) reports cannot outvote the passenger counters.
    """
    if reports_score is None or report_count <= 0:
        return round(occupancy_pct, 1)
    weight = REPORT_WEIGHT * min(1.0, report_count / REPORTS_FOR_FULL_WEIGHT)
    return round((1 - weight) * occupancy_pct + weight * reports_score, 1)


def is_peak_hour(moment: datetime) -> bool:
    t = moment.time()
    return any(start <= t < end for start, end in PEAK_PERIODS)


def is_sustained(
    snapshots: list[tuple[datetime, DensityLevel]],
    now: datetime,
    window: timedelta,
    predicate,
) -> bool:
    """True when every snapshot in the last `window` satisfies `predicate` and the data covers the whole window.

    `snapshots` must be ordered newest first.
    """
    for computed_at, level in snapshots:
        if not predicate(level):
            return False
        if now - computed_at >= window:
            return True
    return False


def suggested_extra_buses(score: float, active_buses: int) -> int:
    """Rough fleet sizing: enough buses to bring the line back to the high threshold."""
    if active_buses <= 0:
        return 1
    needed = active_buses * score / HIGH_THRESHOLD - active_buses
    return max(1, min(5, math.ceil(needed)))


def eta_seconds(distance_m: float, speed_kmh: float, stops_between: int, dwell_left_s: float = 0.0) -> int:
    speed = max(speed_kmh, MIN_SPEED_KMH) / 3.6
    return round(distance_m / speed + stops_between * STOP_DWELL_SECONDS + dwell_left_s)
