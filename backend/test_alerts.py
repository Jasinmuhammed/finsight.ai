from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from threading import Event

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend import alert_scheduler
from backend.alerts import AlertPollResult
from backend.alerts import poll_alerts
from backend.database import Base
from backend.market_data import OHLCVCandle, ProviderUnavailable
from backend.models import Alert, AlertEvent, InstrumentRecord, User


class StaticProvider:
    def __init__(self, candles: list[OHLCVCandle]) -> None:
        self.candles = candles

    def historical_daily_candles(self, *_args, **_kwargs) -> list[OHLCVCandle]:
        return self.candles


class UnavailableProvider(StaticProvider):
    def historical_daily_candles(self, *_args, **_kwargs) -> list[OHLCVCandle]:
        raise ProviderUnavailable("No CSV file for this symbol.")


def make_candle(timestamp: datetime, close: float = 110) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=timestamp,
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=100,
    )


def make_database() -> tuple:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def add_user_alert(database: Session, email: str, created_at: datetime) -> Alert:
    user = User(email=email, password_hash="test-hash")
    instrument = InstrumentRecord(
        symbol=email.split("@")[0].upper()[:32],
        exchange="NSE",
        name="Sample",
        currency="INR",
        data_source="user_entered",
    )
    database.add_all([user, instrument])
    database.flush()
    alert = Alert(
        user_id=user.id,
        instrument_id=instrument.id,
        condition={"operator": "ABOVE", "target_price": 100},
        cooldown_seconds=3600,
        enabled=True,
        created_at=created_at,
    )
    database.add(alert)
    database.commit()
    return alert


def test_alert_poll_deduplicates_events_by_historical_bar():
    engine, database = make_database()
    try:
        created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        now = datetime(2024, 1, 2, 16, tzinfo=timezone.utc)
        alert = add_user_alert(database, "owner@example.com", created_at)
        provider = StaticProvider([make_candle(datetime(2024, 1, 2, 15, tzinfo=timezone.utc))])

        assert poll_alerts(
            database, provider, user_id=alert.user_id, now=now
        ).created_events == 1
        assert poll_alerts(
            database, provider, user_id=alert.user_id, now=now
        ).created_events == 0
        events = list(database.scalars(select(AlertEvent)))
        assert len(events) == 1
        assert events[0].data_timestamp.replace(tzinfo=timezone.utc) == datetime(
            2024, 1, 2, 15, tzinfo=timezone.utc
        )
        assert "historical close above" in events[0].message
    finally:
        database.close()
        engine.dispose()


def test_alert_poll_skips_stale_or_pre_alert_history():
    engine, database = make_database()
    try:
        created_at = datetime(2024, 1, 2, 16, tzinfo=timezone.utc)
        alert = add_user_alert(database, "owner@example.com", created_at)
        stale_provider = StaticProvider(
            [make_candle(datetime(2024, 1, 1, 15, tzinfo=timezone.utc))]
        )
        current_time = datetime(2024, 1, 10, tzinfo=timezone.utc)
        assert poll_alerts(
            database, stale_provider, user_id=alert.user_id, now=current_time
        ).created_events == 0
        assert list(database.scalars(select(AlertEvent))) == []
    finally:
        database.close()
        engine.dispose()


def test_alert_poll_reports_alerts_skipped_without_history():
    engine, database = make_database()
    try:
        alert = add_user_alert(
            database,
            "owner@example.com",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        result = poll_alerts(
            database,
            UnavailableProvider([]),
            user_id=alert.user_id,
            now=datetime(2024, 1, 2, 16, tzinfo=timezone.utc),
        )
        assert result.created_events == 0
        assert result.skipped_alerts == 1
    finally:
        database.close()
        engine.dispose()


def test_alert_poll_is_scoped_to_requested_user():
    engine, database = make_database()
    try:
        created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        owner_alert = add_user_alert(database, "owner@example.com", created_at)
        other_alert = add_user_alert(database, "other@example.com", created_at)
        provider = StaticProvider([make_candle(datetime(2024, 1, 2, 15, tzinfo=timezone.utc))])
        now = datetime(2024, 1, 2, 16, tzinfo=timezone.utc)
        assert poll_alerts(
            database, provider, user_id=owner_alert.user_id, now=now
        ).created_events == 1
        events = list(database.scalars(select(AlertEvent)))
        assert len(events) == 1
        assert events[0].alert_id == owner_alert.id
        assert events[0].alert_id != other_alert.id
    finally:
        database.close()
        engine.dispose()


def test_alert_cooldown_suppresses_another_bar_until_elapsed():
    engine, database = make_database()
    try:
        created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        alert = add_user_alert(database, "owner@example.com", created_at)
        first_bar = make_candle(datetime(2024, 1, 2, 15, tzinfo=timezone.utc))
        second_bar = make_candle(datetime(2024, 1, 2, 15, 30, tzinfo=timezone.utc))
        provider = StaticProvider([first_bar])
        first_poll = datetime(2024, 1, 2, 16, tzinfo=timezone.utc)
        assert poll_alerts(
            database, provider, user_id=alert.user_id, now=first_poll
        ).created_events == 1

        provider.candles = [second_bar]
        assert poll_alerts(
            database,
            provider,
            user_id=alert.user_id,
            now=first_poll + timedelta(minutes=30),
        ).created_events == 0
        assert poll_alerts(
            database,
            provider,
            user_id=alert.user_id,
            now=first_poll + timedelta(hours=2),
        ).created_events == 1
    finally:
        database.close()
        engine.dispose()


def test_scheduler_runs_a_poll_and_stops_cleanly(monkeypatch):
    polled = Event()
    monkeypatch.setattr(
        alert_scheduler, "SessionLocal", lambda: nullcontext(object())
    )
    monkeypatch.setattr(
        alert_scheduler, "get_market_data_provider", lambda: object()
    )
    monkeypatch.setattr(
        alert_scheduler,
        "poll_alerts",
        lambda *_args: (polled.set(), AlertPollResult(0, 0))[1],
    )
    scheduler = alert_scheduler.AlertScheduler(interval_seconds=60)
    scheduler.start()
    try:
        assert polled.wait(timeout=2)
    finally:
        scheduler.stop()
    assert scheduler._thread is None
