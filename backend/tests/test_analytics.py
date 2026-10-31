from datetime import timedelta

import pytest

from app.business.analytics_service import AnalyticsService
from app.domain.enums import AlertStatus, BusStatus, DensityLevel, ReportSource
from app.domain.models import CrowdReport

from .conftest import START


@pytest.fixture
def analytics(repos):
    return AnalyticsService(
        repos.network, repos.buses, repos.reports, repos.density, repos.alerts,
        alert_window=timedelta(minutes=10), resolve_window=timedelta(minutes=5),
        report_window=timedelta(minutes=10),
    )


def set_load(repos, line_id, percent, status=BusStatus.IN_SERVICE, only=None):
    buses = repos.buses.list_by_line(line_id)
    for bus in buses[:only]:
        bus.passenger_count = round(bus.passenger_limit * percent / 100)
        bus.status = status
    repos.buses.save_live_state(buses)


def run_minutes(analytics, minutes):
    for minute in minutes:
        analytics.run(START + timedelta(minutes=minute))


def open_alerts(repos):
    return repos.alerts.list(AlertStatus.OPEN)


@pytest.fixture
def crowded_line_1(repos):
    set_load(repos, 1, 100)   # overcrowded
    set_load(repos, 2, 10)    # nearly empty, 1 km away: the donor
    set_load(repos, 3, 60)    # medium


def test_density_levels_per_line(repos, analytics, crowded_line_1):
    snapshots = {s.line_id: s for s in analytics.compute_density(START)}
    assert snapshots[1].level == DensityLevel.HIGH
    assert snapshots[2].level == DensityLevel.LOW
    assert snapshots[3].level == DensityLevel.MEDIUM
    assert snapshots[1].active_buses == 4


def test_alert_only_after_ten_minutes_of_high_density(repos, analytics, crowded_line_1):
    run_minutes(analytics, range(0, 10))   # minutes 0..9
    assert open_alerts(repos) == []
    run_minutes(analytics, [10])
    alerts = open_alerts(repos)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.line_id == 1
    assert "Əlavə avtobus ehtiyatı ayrılmalıdır" in alert.message
    assert alert.suggested_donor_line_id == 2
    assert alert.suggested_bus_count == 1   # 4 buses at 100% -> one more brings it to ~85%
    assert alert.created_at == START + timedelta(minutes=10)


def test_dip_below_high_restarts_the_ten_minutes(repos, analytics, crowded_line_1):
    run_minutes(analytics, range(0, 6))
    set_load(repos, 1, 70)
    run_minutes(analytics, [6])
    set_load(repos, 1, 100)
    run_minutes(analytics, range(7, 17))   # high again from minute 7
    assert open_alerts(repos) == []
    run_minutes(analytics, [17])
    assert [a.line_id for a in open_alerts(repos)] == [1]


def test_no_duplicate_alert_while_one_is_open(repos, analytics, crowded_line_1):
    run_minutes(analytics, range(0, 20))
    assert len(repos.alerts.list()) == 1


def test_alert_resolves_after_five_calm_minutes(repos, analytics, crowded_line_1):
    run_minutes(analytics, range(0, 11))
    set_load(repos, 1, 50)
    run_minutes(analytics, range(11, 16))
    assert len(open_alerts(repos)) == 1
    run_minutes(analytics, [16])
    alert = repos.alerts.list()[0]
    assert alert.status == AlertStatus.RESOLVED
    assert alert.resolved_by == "system"


def test_buses_on_layover_do_not_lower_the_line_average(repos, analytics):
    set_load(repos, 1, 100)
    set_load(repos, 1, 0, status=BusStatus.LAYOVER, only=2)  # two empty buses resting at the terminal
    snapshot = next(s for s in analytics.compute_density(START) if s.line_id == 1)
    assert snapshot.occupancy_pct == 100
    assert snapshot.level == DensityLevel.HIGH


def test_passenger_reports_can_tip_a_line_into_high(repos, analytics):
    set_load(repos, 3, 84)
    assert next(s for s in analytics.compute_density(START) if s.line_id == 3).level == DensityLevel.MEDIUM
    repos.reports.add_many([
        CrowdReport(line_id=3, level=DensityLevel.HIGH, reported_at=START - timedelta(minutes=2),
                    source=ReportSource.PASSENGER)
        for _ in range(5)
    ])
    snapshot = next(s for s in analytics.compute_density(START) if s.line_id == 3)
    assert snapshot.report_score == 95
    assert snapshot.level == DensityLevel.HIGH


def test_old_reports_are_ignored(repos, analytics):
    set_load(repos, 3, 84)
    repos.reports.add(CrowdReport(line_id=3, level=DensityLevel.HIGH, reported_at=START - timedelta(minutes=11),
                                  source=ReportSource.PASSENGER))
    snapshot = next(s for s in analytics.compute_density(START) if s.line_id == 3)
    assert snapshot.report_score is None


def test_no_donor_when_no_line_is_underused(repos, analytics):
    set_load(repos, 1, 100)
    set_load(repos, 2, 70)
    set_load(repos, 3, 70)
    run_minutes(analytics, range(0, 11))
    alert = open_alerts(repos)[0]
    assert alert.suggested_donor_line_id is None
    assert "yönləndirilə bilər" not in alert.message
