from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.market_data import MarketDataProvider, ProviderUnavailable
from backend.models import Alert, AlertEvent, InstrumentRecord


MAX_BAR_AGE = timedelta(days=4)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertPollResult:
    created_events: int
    skipped_alerts: int


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def poll_alerts(
    database: Session,
    provider: MarketDataProvider,
    *,
    user_id: str | None = None,
    now: datetime | None = None,
) -> AlertPollResult:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    query = (
        select(Alert, InstrumentRecord)
        .join(InstrumentRecord, InstrumentRecord.id == Alert.instrument_id)
        .where(Alert.enabled.is_(True))
        .order_by(Alert.created_at, Alert.id)
    )
    if user_id is not None:
        query = query.where(Alert.user_id == user_id)

    created_count = 0
    skipped_count = 0
    for alert, instrument in database.execute(query).all():
        try:
            candles = provider.historical_daily_candles(
                instrument.symbol, instrument.exchange, None, None
            )
        except (ProviderUnavailable, ValueError) as error:
            logger.warning(
                "Skipped alert %s for %s:%s: %s",
                alert.id,
                instrument.exchange,
                instrument.symbol,
                error,
            )
            skipped_count += 1
            continue
        if not candles:
            continue
        candle = candles[-1]
        candle_time = _as_utc(candle.timestamp)
        alert_created = _as_utc(alert.created_at)
        if (
            candle_time <= alert_created
            or candle_time > current_time
            or current_time - candle_time > MAX_BAR_AGE
        ):
            continue

        condition = alert.condition
        target = float(condition["target_price"])
        operator = condition["operator"]
        triggered = (
            candle.close >= target
            if operator == "ABOVE"
            else candle.close <= target
        )
        if not triggered:
            continue

        cooldown_start = current_time - timedelta(seconds=alert.cooldown_seconds)
        recent_event = database.scalar(
            select(AlertEvent.id).where(
                AlertEvent.alert_id == alert.id,
                AlertEvent.created_at >= cooldown_start,
            )
        )
        if recent_event:
            continue

        event = AlertEvent(
            alert_id=alert.id,
            message=(
                f"{instrument.exchange}:{instrument.symbol} historical close "
                f"{operator.lower()} {target:g}"
            ),
            triggered_value=candle.close,
            data_timestamp=candle_time,
            created_at=current_time,
        )
        database.add(event)
        try:
            database.commit()
        except IntegrityError:
            database.rollback()
            duplicate = database.scalar(
                select(AlertEvent.id).where(
                    AlertEvent.alert_id == alert.id,
                    AlertEvent.data_timestamp == candle_time,
                )
            )
            if duplicate is None:
                raise
            continue
        created_count += 1
    return AlertPollResult(created_events=created_count, skipped_alerts=skipped_count)
