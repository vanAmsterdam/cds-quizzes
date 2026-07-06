from __future__ import annotations

from datetime import datetime

from cds_quizzes.database import database_now
from cds_quizzes.timezone import APP_TIMEZONE, amsterdam_now


def test_database_now_uses_amsterdam_time_for_sqlite(db):
    value = database_now(db)
    expected = amsterdam_now()

    assert abs((expected - value).total_seconds()) < 5


def test_amsterdam_now_is_naive_local_app_time():
    value = amsterdam_now()
    aware_expected = datetime.now(APP_TIMEZONE).replace(tzinfo=None)

    assert value.tzinfo is None
    assert abs((aware_expected - value).total_seconds()) < 5
