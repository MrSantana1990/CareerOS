import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.anti_spam import applications_submitted_today, remaining_daily_quota  # noqa: E402

TODAY = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)


def test_counts_only_applied_status_submitted_today() -> None:
    applications = [
        {"status": "APPLIED", "submitted_at": "2026-08-22T09:00:00+00:00"},
        {"status": "APPLIED", "submitted_at": "2026-08-22T12:00:00+00:00"},
        {"status": "READY_FOR_REVIEW", "submitted_at": None},
    ]
    assert applications_submitted_today(applications, TODAY) == 2


def test_ignores_applications_submitted_on_other_days() -> None:
    applications = [
        {"status": "APPLIED", "submitted_at": "2026-08-21T09:00:00+00:00"},
        {"status": "APPLIED", "submitted_at": "2026-08-20T09:00:00+00:00"},
    ]
    assert applications_submitted_today(applications, TODAY) == 0


def test_ignores_applications_without_submitted_at() -> None:
    applications = [{"status": "APPLIED", "submitted_at": None}]
    assert applications_submitted_today(applications, TODAY) == 0


def test_remaining_quota_subtracts_todays_submissions() -> None:
    applications = [{"status": "APPLIED", "submitted_at": "2026-08-22T09:00:00+00:00"} for _ in range(5)]
    assert remaining_daily_quota(applications, 20, TODAY) == 15


def test_remaining_quota_never_goes_negative() -> None:
    applications = [{"status": "APPLIED", "submitted_at": "2026-08-22T09:00:00+00:00"} for _ in range(25)]
    assert remaining_daily_quota(applications, 20, TODAY) == 0


def test_remaining_quota_full_when_nothing_submitted_today() -> None:
    assert remaining_daily_quota([], 20, TODAY) == 20


def test_third_daily_run_cannot_exceed_the_configured_target() -> None:
    """Regressao do bug real: 3 execucoes/dia nao podem, juntas, ultrapassar daily_target."""
    applications: list[dict] = []
    daily_target = 20
    total_submitted = 0
    for _ in range(3):
        quota = remaining_daily_quota(applications, daily_target, TODAY)
        submitted_this_run = min(quota, 20)
        for _ in range(submitted_this_run):
            applications.append({"status": "APPLIED", "submitted_at": TODAY.isoformat()})
        total_submitted += submitted_this_run
    assert total_submitted == daily_target
