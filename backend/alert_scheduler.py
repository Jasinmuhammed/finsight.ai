import logging
import os
from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from backend.alerts import poll_alerts
from backend.database import SessionLocal
from backend.market_data import ProviderUnavailable, get_market_data_provider


logger = logging.getLogger(__name__)


class AlertScheduler:
    def __init__(self, interval_seconds: int) -> None:
        if interval_seconds < 0:
            raise ValueError("ALERT_POLL_INTERVAL_SECONDS cannot be negative.")
        self.interval_seconds = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self.interval_seconds == 0:
            logger.info("Alert polling scheduler is disabled.")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="finsight-alert-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with SessionLocal() as database:
                    result = poll_alerts(database, get_market_data_provider())
                if result.created_events:
                    logger.info(
                        "Alert polling created %s historical events.",
                        result.created_events,
                    )
            except ProviderUnavailable as error:
                logger.warning("Alert polling skipped: %s", error)
            except (OSError, SQLAlchemyError, UnicodeError, ValueError):
                logger.exception("Alert polling failed.")
            self._stop.wait(self.interval_seconds)


def create_alert_scheduler() -> AlertScheduler:
    try:
        interval = int(os.getenv("ALERT_POLL_INTERVAL_SECONDS", "300"))
    except ValueError as error:
        raise ValueError("ALERT_POLL_INTERVAL_SECONDS must be an integer.") from error
    return AlertScheduler(interval)
