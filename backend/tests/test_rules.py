from datetime import datetime, timedelta

import pytest

from app.domain import rules
from app.domain.enums import DensityLevel

LOW, MEDIUM, HIGH = DensityLevel.LOW, DensityLevel.MEDIUM, DensityLevel.HIGH


@pytest.mark.parametrize("score, level", [
    (0, LOW), (49.9, LOW), (50, MEDIUM), (85, MEDIUM), (85.1, HIGH), (100, HIGH),
])
def test_density_level_thresholds(score, level):
    assert rules.density_level(score) == level


def test_report_score_averages_level_scores():
    assert rules.report_score([]) is None
    assert rules.report_score([HIGH]) == 95
    assert rules.report_score([LOW, HIGH]) == 60


def test_density_score_uses_occupancy_only_without_reports():
    assert rules.density_score(72.34, None) == 72.3
    assert rules.density_score(72.0, 95.0, report_count=0) == 72.0


def test_density_score_report_weight_grows_with_report_count():
    # 2 reports: weight 0.3 * 2/5 = 0.12
    assert rules.density_score(50.0, 100.0, report_count=2) == pytest.approx(0.88 * 50 + 0.12 * 100, abs=0.05)
    # 5 or more reports: full weight 0.3
    full = 0.7 * 50 + 0.3 * 100
    assert rules.density_score(50.0, 100.0, report_count=5) == pytest.approx(full, abs=0.05)
    assert rules.density_score(50.0, 100.0, report_count=50) == pytest.approx(full, abs=0.05)


def test_few_wrong_reports_cannot_outvote_full_buses():
    # Buses are full; two passengers wrongly report "low".
    score = rules.density_score(98.0, rules.report_score([LOW, LOW]), report_count=2)
    assert rules.density_level(score) == HIGH


@pytest.mark.parametrize("clock, peak", [
    ("07:29", False), ("07:30", True), ("09:29", True), ("09:30", False),
    ("13:00", False), ("17:30", True), ("19:29", True), ("19:30", False),
])
def test_is_peak_hour(clock, peak):
    hour, minute = map(int, clock.split(":"))
    assert rules.is_peak_hour(datetime(2026, 10, 31, hour, minute)) is peak


def minutes_ago(now, levels):
    """[(level for now), (level 1 min ago), ...] -> snapshots newest first."""
    return [(now - timedelta(minutes=i), level) for i, level in enumerate(levels)]


class TestIsSustained:
    now = datetime(2026, 10, 31, 8, 30)
    window = timedelta(minutes=10)

    def high(self, level):
        return level == HIGH

    def test_true_when_every_snapshot_in_window_is_high(self):
        snapshots = minutes_ago(self.now, [HIGH] * 11)
        assert rules.is_sustained(snapshots, self.now, self.window, self.high)

    def test_false_when_history_shorter_than_window(self):
        snapshots = minutes_ago(self.now, [HIGH] * 10)  # covers only 9 minutes
        assert not rules.is_sustained(snapshots, self.now, self.window, self.high)

    def test_false_when_one_snapshot_in_window_is_not_high(self):
        levels = [HIGH] * 11
        levels[4] = MEDIUM
        assert not rules.is_sustained(minutes_ago(self.now, levels), self.now, self.window, self.high)

    def test_older_snapshots_outside_window_are_ignored(self):
        levels = [HIGH] * 11 + [LOW, LOW]
        assert rules.is_sustained(minutes_ago(self.now, levels), self.now, self.window, self.high)

    def test_false_without_data(self):
        assert not rules.is_sustained([], self.now, self.window, self.high)


@pytest.mark.parametrize("score, buses, expected", [
    (86, 10, 1),     # barely high -> at least one bus
    (100, 10, 2),    # 10 * 100/85 - 10 = 1.76 -> 2
    (100, 40, 5),    # capped at 5
    (95, 0, 1),      # no active buses -> one
])
def test_suggested_extra_buses(score, buses, expected):
    assert rules.suggested_extra_buses(score, buses) == expected


def test_eta_seconds():
    # 1 km at 36 km/h = 100 s, plus 2 intermediate stops * 30 s
    assert rules.eta_seconds(1000, 36, stops_between=2) == 160


def test_eta_uses_minimum_speed_for_stopped_bus():
    assert rules.eta_seconds(500, 0, stops_between=0) == round(500 / (rules.MIN_SPEED_KMH / 3.6))
