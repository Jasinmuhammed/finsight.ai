import csv
import os
import re
import threading
import time
from functools import lru_cache
from datetime import date, datetime, time as day_time, timezone
from pathlib import Path
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")
CACHE_TTL_SECONDS = 300
MAX_CSV_ROWS = 100_000
MAX_INSTRUMENT_FILES = 1_000
MAX_CACHED_CANDLES = 5_000


class ProviderUnavailable(Exception):
    pass


class InstrumentMetadata(BaseModel):
    symbol: str
    exchange: Literal["NSE", "BSE"]
    name: str
    currency: Literal["INR"] = "INR"

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid instrument symbol")
        return normalized


class OHLCVCandle(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: int = Field(ge=0)

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Candle timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "OHLCVCandle":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("Candle high must be at least open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Candle low must be at most open, close, and high")
        return self


class HistoricalCandles(BaseModel):
    symbol: str
    exchange: Literal["NSE", "BSE"]
    timeframe: Literal["1d"]
    candles: list[OHLCVCandle]
    data_status: Literal["HISTORICAL"]
    source: str
    data_as_of: datetime | None
    provenance_note: str


class MarketDataProvider(Protocol):
    name: str

    def status(self) -> dict[str, str | bool]: ...

    def search_instruments(self, query: str, limit: int) -> list[InstrumentMetadata]: ...

    def historical_daily_candles(
        self,
        symbol: str,
        exchange: str,
        start: date | None,
        end: date | None,
    ) -> list[OHLCVCandle]: ...


class UnconfiguredProvider:
    name = "unconfigured"

    def status(self) -> dict[str, str | bool]:
        return {
            "provider": os.getenv("MARKET_DATA_PROVIDER", "demo"),
            "status": "UNAVAILABLE",
            "configured": False,
            "message": "No historical market-data provider is configured.",
        }

    def search_instruments(self, query: str, limit: int) -> list[InstrumentMetadata]:
        raise ProviderUnavailable("Configure a market-data provider to search instruments.")

    def historical_daily_candles(
        self,
        symbol: str,
        exchange: str,
        start: date | None,
        end: date | None,
    ) -> list[OHLCVCandle]:
        raise ProviderUnavailable("Configure a market-data provider to retrieve candles.")


class UserCSVProvider:
    name = "user_csv"

    def __init__(self, directory: str) -> None:
        self.directory = Path(directory).expanduser().resolve()
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def status(self) -> dict[str, str | bool]:
        configured = self.directory.is_dir()
        return {
            "provider": self.name,
            "status": "HISTORICAL" if configured else "UNAVAILABLE",
            "configured": configured,
            "message": (
                "User-supplied daily CSV files; source provenance is not independently verified."
                if configured
                else "CSV directory is not configured or does not exist."
            ),
        }

    def _get_cache(self, key: tuple, source_revision: float):
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry and now - entry[0] < CACHE_TTL_SECONDS and entry[1][0] == source_revision:
                return entry[1][1]
        return None

    def _set_cache(self, key: tuple, source_revision: float, value: object) -> None:
        with self._lock:
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (
                time.monotonic(),
                (source_revision, value),
            )

    def _files(self) -> list[Path]:
        if not self.directory.is_dir():
            raise ProviderUnavailable(
                "CSV provider is selected, but MARKET_DATA_CSV_DIR is not an available directory."
            )
        files = []
        for path in self.directory.glob("*.csv"):
            if path.is_file() and path.resolve().parent == self.directory:
                files.append(path)
                if len(files) > MAX_INSTRUMENT_FILES:
                    raise ProviderUnavailable(
                        f"CSV provider supports at most {MAX_INSTRUMENT_FILES} instrument files."
                    )
        return sorted(files)

    def search_instruments(self, query: str, limit: int = 50) -> list[InstrumentMetadata]:
        normalized = query.strip().upper()
        files = self._files()
        revision = max(
            [self.directory.stat().st_mtime, *(path.stat().st_mtime for path in files)]
        )
        key = ("search", normalized, limit)
        cached = self._get_cache(key, revision)
        if cached is not None:
            return cached

        found = []
        for path in files:
            match = re.fullmatch(r"(NSE|BSE)_([A-Z0-9][A-Z0-9._-]{0,31})", path.stem.upper())
            if not match:
                continue
            exchange, symbol = match.groups()
            instrument = InstrumentMetadata(
                symbol=symbol,
                exchange=exchange,
                name=symbol,
            )
            if not normalized or normalized in symbol:
                found.append(instrument)
        found.sort(key=lambda item: (item.exchange, item.symbol))
        result = found[:limit]
        self._set_cache(key, revision, result)
        return result

    def _csv_path(self, symbol: str, exchange: str) -> Path:
        normalized_symbol = symbol.strip().upper()
        normalized_exchange = exchange.strip().upper()
        if not SYMBOL_PATTERN.fullmatch(normalized_symbol) or normalized_exchange not in {"NSE", "BSE"}:
            raise ValueError("Invalid exchange or instrument symbol")
        if not self.directory.is_dir():
            raise ProviderUnavailable(
                "CSV provider is selected, but MARKET_DATA_CSV_DIR is not an available directory."
            )
        path = self.directory / f"{normalized_exchange}_{normalized_symbol}.csv"
        resolved = path.resolve()
        if resolved.parent != self.directory or not resolved.is_file():
            raise ProviderUnavailable(
                f"No user-supplied daily candle file is available for {normalized_exchange}:{normalized_symbol}."
            )
        return resolved

    def historical_daily_candles(
        self,
        symbol: str,
        exchange: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[OHLCVCandle]:
        path = self._csv_path(symbol, exchange)
        if start and end and start > end:
            raise ValueError("start date must be on or before end date")
        revision = path.stat().st_mtime
        key = ("candles", path.name, start, end)
        cached = self._get_cache(key, revision)
        if cached is not None:
            return cached

        candles: list[OHLCVCandle] = []
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = {column.strip().lower() for column in (reader.fieldnames or [])}
            required = {"date", "open", "high", "low", "close", "volume"}
            if not required.issubset(columns):
                raise ValueError(
                    "CSV requires Date, Open, High, Low, Close, and Volume columns."
                )
            for row_number, row in enumerate(reader, start=2):
                if row_number > MAX_CSV_ROWS + 1:
                    raise ValueError(f"CSV exceeds the {MAX_CSV_ROWS} row limit.")
                normalized = {
                    str(key).strip().lower(): value for key, value in row.items() if key
                }
                try:
                    timestamp_text = normalized["date"].strip().replace("Z", "+00:00")
                    timestamp = datetime.fromisoformat(timestamp_text)
                    if timestamp.tzinfo is None:
                        timestamp = (
                            datetime.combine(
                                timestamp.date(), day_time(15, 30), tzinfo=MARKET_TIMEZONE
                            )
                            if len(timestamp_text) == 10
                            else timestamp.replace(tzinfo=MARKET_TIMEZONE)
                        )
                    candle = OHLCVCandle(
                        timestamp=timestamp,
                        open=float(normalized["open"]),
                        high=float(normalized["high"]),
                        low=float(normalized["low"]),
                        close=float(normalized["close"]),
                        volume=int(normalized["volume"]),
                    )
                except (ValueError, TypeError, KeyError) as error:
                    raise ValueError(f"Invalid candle data on CSV row {row_number}.") from error
                if start and candle.timestamp.date() < start:
                    continue
                if end and candle.timestamp.date() > end:
                    continue
                candles.append(candle)

        candles.sort(key=lambda candle: candle.timestamp)
        if len({candle.timestamp for candle in candles}) != len(candles):
            raise ValueError("CSV contains duplicate candle timestamps.")
        market_dates = [
            candle.timestamp.astimezone(MARKET_TIMEZONE).date() for candle in candles
        ]
        if len(set(market_dates)) != len(market_dates):
            raise ValueError(
                "Daily CSV may contain only one candle per Asia/Kolkata market date."
            )
        if len(candles) <= MAX_CACHED_CANDLES:
            self._set_cache(key, revision, candles)
        return candles


@lru_cache(maxsize=1)
def get_market_data_provider() -> MarketDataProvider:
    provider = os.getenv("MARKET_DATA_PROVIDER", "demo").strip().lower()
    if provider == "csv":
        directory = os.getenv("MARKET_DATA_CSV_DIR", "").strip()
        if directory:
            return UserCSVProvider(directory)
    return UnconfiguredProvider()
