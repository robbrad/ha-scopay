"""Tests for the SCOPAY spend analysis derived from the transaction table."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from custom_components.scopay import sensor
from custom_components.scopay.parse import ScopayData, Transaction


def _txn(days_ago: int, amount: float, description: str = "Cashless Catering"):
    """A transaction dated `days_ago` days before the frozen 'today'."""
    when = date(2026, 9, 7) - timedelta(days=days_ago)
    return Transaction(
        date=f"{when.day} {when.strftime('%b')} {when.year}",
        description=description,
        amount=amount,
    )


@pytest.fixture(autouse=True)
def frozen_today():
    """Pin 'now' so the day-window maths is deterministic."""

    class _Now:
        @staticmethod
        def date():
            return date(2026, 9, 7)

    with patch.object(sensor.dt_util, "now", return_value=_Now()):
        yield


@pytest.fixture
def data():
    """A pupil who spent on three days and topped up once."""
    return ScopayData(
        transactions=[
            _txn(1, -2.40),
            _txn(1, -0.60),  # same day, second purchase
            _txn(3, -3.10),
            _txn(2, 20.00, "Top up"),  # money in, never counted as spend
            _txn(20, -2.00),
            _txn(90, -5.00),  # outside every window
            Transaction(date="unparseable", description="x", amount=-1.00),
            Transaction(date="5 Sept 2026", description="no amount", amount=None),
        ]
    )


def test_spend_total_7d_excludes_topups_and_old_rows(data):
    # 2.40 + 0.60 + 3.10, not the 20.00 top-up nor the 20/90-day-old rows.
    assert sensor._spend_total(data, 7) == 6.10


def test_spend_total_30d(data):
    assert sensor._spend_total(data, 30) == 8.10


def test_spend_total_is_zero_when_nothing_matches():
    assert sensor._spend_total(ScopayData(), 7) == 0.0


def test_avg_is_per_spend_day_not_per_calendar_day(data):
    # Three distinct spend days in 30 days: 8.10 / 3, not 8.10 / 30.
    assert sensor._avg_per_school_day(data) == 2.7


def test_avg_is_none_without_spend():
    assert sensor._avg_per_school_day(ScopayData()) is None


def test_projected_monthly(data):
    assert sensor._projected_monthly(data) == pytest.approx(
        2.7 * sensor.SCHOOL_DAYS_PER_MONTH
    )


def test_projected_monthly_is_none_without_spend():
    assert sensor._projected_monthly(ScopayData()) is None


def test_spend_attrs_reports_days_and_caps_recent(data):
    attrs = sensor._spend_attrs(data)
    assert attrs["spend_days"] == 3
    assert attrs["transactions"] == 4
    assert len(attrs["recent"]) <= 10
