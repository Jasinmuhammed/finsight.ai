import csv
import json
import logging
import math
import os
import re
import threading
import time
from functools import lru_cache
from datetime import date, datetime, time as day_time, timedelta, timezone
from pathlib import Path
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import yfinance
from curl_cffi.requests.exceptions import RequestException as CurlRequestException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from yfinance.exceptions import YFException

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")
CACHE_TTL_SECONDS = 300
MAX_CSV_ROWS = 100_000
MAX_INSTRUMENT_FILES = 1_000
MAX_CACHED_CANDLES = 5_000
MAX_PROVIDER_RESPONSE_BYTES = 2_000_000
MAX_FINNHUB_UNIVERSE_SIZE = 50
FINNHUB_API_BASE = "https://finnhub.io/api/v1"
MAX_RECENT_HISTORY_AGE = timedelta(days=4)
MAX_YAHOO_HISTORY_DAYS = 365 * 20
YAHOO_NSE_TICKERS = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
}
logger = logging.getLogger(__name__)


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
    freshness_status: Literal["RECENT_HISTORY", "STALE_HISTORY", "UNKNOWN"]
    source: str
    data_as_of: datetime | None
    provenance_note: str


class MarketDataProvider(Protocol):
    name: str
    source_label: str
    provenance_note: str

    def status(self) -> dict[str, str | bool]: ...

    def search_instruments(self, query: str, limit: int) -> list[InstrumentMetadata]: ...

    def historical_daily_candles(
        self,
        symbol: str,
        exchange: str,
        start: date | None,
        end: date | None,
    ) -> list[OHLCVCandle]: ...


def historical_freshness(data_as_of: datetime | None) -> str:
    if data_as_of is None:
        return "UNKNOWN"
    timestamp = (
        data_as_of.replace(tzinfo=timezone.utc)
        if data_as_of.tzinfo is None
        else data_as_of.astimezone(timezone.utc)
    )
    age = (
        datetime.now(MARKET_TIMEZONE).date()
        - timestamp.astimezone(MARKET_TIMEZONE).date()
    )
    if age.days < 0:
        return "UNKNOWN"
    return (
        "RECENT_HISTORY"
        if age <= MAX_RECENT_HISTORY_AGE
        else "STALE_HISTORY"
    )


class UnconfiguredProvider:
    name = "unconfigured"
    source_label = "No market-data provider configured"
    provenance_note = "No historical market data is configured."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or "No historical market-data provider is configured."

    def status(self) -> dict[str, str | bool]:
        return {
            "provider": os.getenv("MARKET_DATA_PROVIDER", "demo"),
            "status": "UNAVAILABLE",
            "configured": False,
            "message": self.message,
        }

    def search_instruments(self, query: str, limit: int) -> list[InstrumentMetadata]:
        raise ProviderUnavailable(self.message)

    def historical_daily_candles(
        self,
        symbol: str,
        exchange: str,
        start: date | None,
        end: date | None,
    ) -> list[OHLCVCandle]:
        raise ProviderUnavailable(self.message)


class UserCSVProvider:
    name = "user_csv"
    source_label = "User-supplied CSV"
    provenance_note = (
        "User-supplied CSV; source provenance is not independently verified."
    )

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
        seen_timestamps: set[datetime] = set()
        seen_market_dates: set[date] = set()
        previous_timestamp: datetime | None = None
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            normalized_columns = [
                column.strip().lower() for column in (reader.fieldnames or [])
            ]
            columns = set(normalized_columns)
            required = {"date", "open", "high", "low", "close", "volume"}
            if len(columns) != len(normalized_columns):
                raise ValueError("CSV contains duplicate column names.")
            if not required.issubset(columns):
                raise ValueError(
                    "CSV requires Date, Open, High, Low, Close, and Volume columns."
                )
            for row_number, row in enumerate(reader, start=2):
                if row_number > MAX_CSV_ROWS + 1:
                    raise ValueError(f"CSV exceeds the {MAX_CSV_ROWS} row limit.")
                if not isinstance(row, dict) or None in row:
                    raise ValueError(f"Invalid candle data on CSV row {row_number}.")
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
                except (AttributeError, ValueError, TypeError, KeyError) as error:
                    raise ValueError(f"Invalid candle data on CSV row {row_number}.") from error
                if candle.timestamp in seen_timestamps:
                    raise ValueError("CSV contains duplicate candle timestamps.")
                if previous_timestamp is not None and candle.timestamp < previous_timestamp:
                    raise ValueError("CSV candles must be in chronological order.")
                market_date = candle.timestamp.astimezone(MARKET_TIMEZONE).date()
                if market_date in seen_market_dates:
                    raise ValueError(
                        "Daily CSV may contain only one candle per Asia/Kolkata market date."
                    )
                seen_timestamps.add(candle.timestamp)
                seen_market_dates.add(market_date)
                previous_timestamp = candle.timestamp
                if start and market_date < start:
                    continue
                if end and market_date > end:
                    continue
                candles.append(candle)

        if len(candles) <= MAX_CACHED_CANDLES:
            self._set_cache(key, revision, candles)
        return candles


class FinnhubHistoricalProvider:
    name = "finnhub"
    source_label = "Finnhub daily historical candles"
    provenance_note = (
        "Daily historical candles from Finnhub; not live quotes. "
        "Provider timestamps are retained in UTC."
    )

    def __init__(self, api_key: str, configured_symbols: str = "") -> None:
        self._api_key = api_key
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._symbols = self._parse_symbols(configured_symbols)
        self._provider_symbols: dict[tuple[str, str], str] = {}
        self._ambiguous_provider_symbols: set[tuple[str, str]] = set()

    @staticmethod
    def _parse_symbols(value: str) -> list[InstrumentMetadata]:
        symbols: dict[tuple[str, str], InstrumentMetadata] = {}
        for entry in value.split(","):
            configured = entry.strip().upper()
            if not configured:
                continue
            match = re.fullmatch(r"(NSE|BSE):([A-Z0-9][A-Z0-9._-]{0,31})", configured)
            if not match:
                raise ValueError(
                    "FINNHUB_SYMBOLS entries must use EXCHANGE:SYMBOL format, such as NSE:RELIANCE."
                )
            exchange, symbol = match.groups()
            metadata = InstrumentMetadata(
                symbol=symbol, exchange=exchange, name=symbol
            )
            symbols[(exchange, metadata.symbol)] = metadata
            if len(symbols) > MAX_FINNHUB_UNIVERSE_SIZE:
                raise ValueError(
                    f"FINNHUB_SYMBOLS may contain at most {MAX_FINNHUB_UNIVERSE_SIZE} tickers "
                    "to limit historical API calls per screen."
                )
        return sorted(symbols.values(), key=lambda item: (item.exchange, item.symbol))

    def status(self) -> dict[str, str | bool]:
        return {
            "provider": self.name,
            "status": "HISTORICAL" if self._api_key else "UNAVAILABLE",
            "configured": bool(self._api_key),
            "universe_configured": bool(self._symbols),
            "message": (
                "Finnhub daily historical candles only; not live quotes. "
                "Screener universe is limited to FINNHUB_SYMBOLS."
                if self._symbols
                else "Finnhub daily historical candles only; configure FINNHUB_SYMBOLS for screening. "
                "Not live quotes."
            )
            if self._api_key
            else "Configure FINNHUB_API_KEY to enable Finnhub historical daily candles.",
        }

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise ProviderUnavailable(
                "MARKET_DATA_PROVIDER=finnhub requires FINNHUB_API_KEY."
            )

    def _request_json(self, endpoint: str, params: dict[str, str]) -> dict:
        self._require_api_key()
        query = urlencode({**params, "token": self._api_key})
        request = Request(
            f"{FINNHUB_API_BASE}/{endpoint}?{query}",
            headers={"Accept": "application/json", "User-Agent": "FinSightAI/0.1"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        except HTTPError as error:
            logger.warning(
                "Finnhub request failed with upstream HTTP status %d.",
                error.code,
            )
            if error.code == 429:
                raise ProviderUnavailable(
                    "Finnhub rate limit reached; retry after the provider limit resets."
                ) from error
            if error.code in {401, 403}:
                raise ProviderUnavailable(
                    "Finnhub rejected the configured credentials or endpoint access."
                ) from error
            raise ProviderUnavailable(
                f"Finnhub historical data request failed (HTTP {error.code})."
            ) from error
        except (URLError, TimeoutError) as error:
            raise ProviderUnavailable(
                "Finnhub historical data service could not be reached."
            ) from error
        if len(payload) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ProviderUnavailable("Finnhub response exceeded the size limit.")
        try:
            result = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ProviderUnavailable("Finnhub returned invalid JSON.") from error
        if not isinstance(result, dict):
            raise ProviderUnavailable("Finnhub returned an unexpected response.")
        return result

    def search_instruments(self, query: str, limit: int = 50) -> list[InstrumentMetadata]:
        normalized = query.strip()
        if not normalized:
            self._require_api_key()
            return self._symbols[:limit]
        key = ("search", normalized.upper(), limit)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                return cached[1]

        payload = self._request_json("search", {"q": normalized})
        results = payload.get("result")
        if not isinstance(results, list):
            raise ProviderUnavailable("Finnhub returned an unexpected symbol-search response.")
        found: dict[tuple[str, str], InstrumentMetadata] = {}
        configured_by_symbol: dict[str, set[tuple[str, str]]] = {}
        for instrument in self._symbols:
            configured_by_symbol.setdefault(instrument.symbol, set()).add(
                (instrument.exchange, instrument.symbol)
            )

        for item in results:
            if not isinstance(item, dict):
                continue
            provider_symbol = item.get("symbol")
            if not isinstance(provider_symbol, str):
                continue
            normalized_provider_symbol = provider_symbol.strip().upper()
            match = re.fullmatch(
                r"(NSE|BSE):([A-Z0-9][A-Z0-9._-]{0,31})",
                normalized_provider_symbol,
            )
            if match:
                exchange, symbol = match.groups()
            else:
                configured_matches = configured_by_symbol.get(
                    normalized_provider_symbol, set()
                )
                if len(configured_matches) != 1:
                    continue
                exchange, symbol = next(iter(configured_matches))
            name = item.get("description")
            instrument = InstrumentMetadata(
                symbol=symbol,
                exchange=exchange,
                name=name.strip()[:255] if isinstance(name, str) and name.strip() else symbol,
            )
            identity = (exchange, symbol)
            provider_symbol = provider_symbol.strip()
            with self._lock:
                if identity not in self._ambiguous_provider_symbols:
                    existing_provider_symbol = self._provider_symbols.get(identity)
                    if existing_provider_symbol is None or existing_provider_symbol == provider_symbol:
                        self._provider_symbols[identity] = provider_symbol
                    else:
                        self._provider_symbols.pop(identity, None)
                        self._ambiguous_provider_symbols.add(identity)
            found[identity] = instrument
        query_symbol = normalized.upper()
        for instrument in self._symbols:
            if query_symbol in instrument.symbol:
                found.setdefault((instrument.exchange, instrument.symbol), instrument)
        instruments = sorted(
            found.values(), key=lambda item: (item.exchange, item.symbol)
        )[:limit]
        with self._lock:
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic(), instruments)
        return instruments

    def historical_daily_candles(
        self,
        symbol: str,
        exchange: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[OHLCVCandle]:
        normalized_symbol = symbol.strip().upper()
        normalized_exchange = exchange.strip().upper()
        if (
            not SYMBOL_PATTERN.fullmatch(normalized_symbol)
            or normalized_exchange not in {"NSE", "BSE"}
        ):
            raise ValueError("Invalid exchange or instrument symbol")
        if start and end and start > end:
            raise ValueError("start date must be on or before end date")
        latest_completed_date = (
            datetime.now(MARKET_TIMEZONE).date() - timedelta(days=1)
        )
        end_date = min(end or latest_completed_date, latest_completed_date)
        start_date = start or (end_date - timedelta(days=365 * 5))
        if end_date < start_date:
            return []
        if (end_date - start_date).days > 365 * 20:
            raise ValueError("Finnhub history is limited to a 20-year date range.")
        instrument_key = (normalized_exchange, normalized_symbol)
        with self._lock:
            if instrument_key in self._ambiguous_provider_symbols:
                raise ProviderUnavailable(
                    "Finnhub search returned conflicting symbols for this instrument."
                )
            provider_symbol = self._provider_symbols.get(instrument_key)
        provider_symbol = provider_symbol or f"{normalized_exchange}:{normalized_symbol}"
        key = (
            "candles",
            provider_symbol,
            normalized_exchange,
            normalized_symbol,
            start_date,
            end_date,
        )
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                return cached[1]

        start_timestamp = int(
            datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp()
        )
        end_timestamp = int(
            datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc).timestamp()
        )
        payload = self._request_json(
            "stock/candle",
            {
                "symbol": provider_symbol,
                "resolution": "D",
                "from": str(start_timestamp),
                "to": str(end_timestamp),
            },
        )
        state = payload.get("s")
        if state == "no_data":
            candles: list[OHLCVCandle] = []
        elif state != "ok":
            raise ProviderUnavailable(
                "Finnhub could not provide daily candles for this symbol and date range."
            )
        else:
            columns = [payload.get(field) for field in ("t", "o", "h", "l", "c", "v")]
            if any(not isinstance(column, list) for column in columns):
                raise ProviderUnavailable("Finnhub returned malformed candle columns.")
            if len({len(column) for column in columns}) != 1:
                raise ProviderUnavailable("Finnhub returned mismatched candle columns.")
            if len(columns[0]) > MAX_CACHED_CANDLES:
                raise ProviderUnavailable(
                    f"Finnhub response exceeds the {MAX_CACHED_CANDLES} candle limit."
                )
            candles = []
            try:
                for timestamp, open_price, high, low, close, volume in zip(*columns):
                    parsed_volume = float(volume)
                    if not parsed_volume.is_integer() or parsed_volume < 0:
                        raise ValueError("Daily candle volume must be an integer.")
                    candles.append(
                        OHLCVCandle(
                            timestamp=datetime.fromtimestamp(timestamp, timezone.utc),
                            open=open_price,
                            high=high,
                            low=low,
                            close=close,
                            volume=int(parsed_volume),
                        )
                    )
            except (OverflowError, OSError, TypeError, ValueError) as error:
                raise ProviderUnavailable(
                    "Finnhub returned invalid daily OHLCV values."
                ) from error
            market_dates = [
                candle.timestamp.astimezone(MARKET_TIMEZONE).date()
                for candle in candles
            ]
            if (
                len({candle.timestamp for candle in candles}) != len(candles)
                or len(set(market_dates)) != len(market_dates)
            ):
                raise ProviderUnavailable(
                    "Finnhub returned duplicate daily candle timestamps."
                )
            if any(
                current.timestamp <= previous.timestamp
                for previous, current in zip(candles, candles[1:])
            ):
                raise ProviderUnavailable(
                    "Finnhub returned candles outside chronological order."
                )
            candles = [
                candle
                for candle in candles
                if start_date
                <= candle.timestamp.astimezone(MARKET_TIMEZONE).date()
                <= end_date
            ]

        with self._lock:
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic(), candles)
        return candles


class YahooFinanceHistoricalProvider:
    name = "yahoo"
    source_label = "Yahoo Finance daily historical candles"
    provenance_note = (
        "Daily historical candles retrieved from Yahoo Finance via yfinance; "
        "not live quotes. Yahoo timestamps are interpreted in Asia/Kolkata "
        "and normalized to UTC."
    )

    def __init__(self) -> None:
        self._cache: dict[tuple, tuple[float, list[OHLCVCandle]]] = {}
        self._lock = threading.Lock()

    def status(self) -> dict[str, str | bool]:
        return {
            "provider": self.name,
            "status": "HISTORICAL",
            "configured": True,
            "message": (
                "Yahoo Finance daily historical candles only; not live quotes. "
                "Only explicitly supported NSE symbols are available."
            ),
        }

    def search_instruments(
        self, query: str, limit: int = 50
    ) -> list[InstrumentMetadata]:
        normalized = query.strip().upper()
        instruments = [
            InstrumentMetadata(symbol=symbol, exchange="NSE", name=symbol)
            for symbol in YAHOO_NSE_TICKERS
            if not normalized
            or normalized in symbol
            or normalized == YAHOO_NSE_TICKERS[symbol]
        ]
        return instruments[:limit]

    def historical_daily_candles(
        self,
        symbol: str,
        exchange: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[OHLCVCandle]:
        normalized_symbol = symbol.strip().upper()
        normalized_exchange = exchange.strip().upper()
        if (
            not SYMBOL_PATTERN.fullmatch(normalized_symbol)
            or normalized_exchange != "NSE"
        ):
            raise ValueError("Yahoo Finance supports only validated NSE symbols.")
        yahoo_symbol = YAHOO_NSE_TICKERS.get(normalized_symbol)
        if yahoo_symbol is None:
            raise ProviderUnavailable(
                f"No verified Yahoo Finance symbol mapping is available for NSE:{normalized_symbol}."
            )
        if start and end and start > end:
            raise ValueError("start date must be on or before end date")

        latest_completed_date = (
            datetime.now(MARKET_TIMEZONE).date() - timedelta(days=1)
        )
        end_date = min(end or latest_completed_date, latest_completed_date)
        start_date = start or (end_date - timedelta(days=365 * 5))
        if end_date < start_date:
            return []
        if (end_date - start_date).days > MAX_YAHOO_HISTORY_DAYS:
            raise ValueError("Yahoo Finance history is limited to a 20-year date range.")

        key = ("candles", yahoo_symbol, start_date, end_date)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                return cached[1]

        try:
            history = yfinance.Ticker(yahoo_symbol).history(
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                interval="1d",
                auto_adjust=False,
                actions=False,
                timeout=10,
            )
        except (CurlRequestException, OSError, TimeoutError, YFException) as error:
            raise ProviderUnavailable(
                "Yahoo Finance historical data service could not be reached."
            ) from error

        if history is None:
            candles: list[OHLCVCandle] = []
        elif not all(
            hasattr(history, attribute)
            for attribute in ("empty", "columns", "index", "iterrows")
        ):
            raise ProviderUnavailable(
                "Yahoo Finance returned an invalid daily history response."
            )
        elif history.empty:
            candles = []
        else:
            required_columns = {"Open", "High", "Low", "Close", "Volume"}
            if not required_columns.issubset(history.columns):
                raise ProviderUnavailable(
                    "Yahoo Finance returned incomplete daily OHLCV columns."
                )
            if len(history) > MAX_CACHED_CANDLES:
                raise ProviderUnavailable(
                    f"Yahoo Finance response exceeds the {MAX_CACHED_CANDLES} candle limit."
                )
            if getattr(history.index, "tz", None) is None:
                raise ProviderUnavailable(
                    "Yahoo Finance returned daily timestamps without a timezone."
                )
            if (
                getattr(history.index, "has_duplicates", True)
                or not getattr(history.index, "is_monotonic_increasing", False)
            ):
                raise ProviderUnavailable(
                    "Yahoo Finance returned duplicate or out-of-order daily timestamps."
                )

            candles = []
            try:
                for timestamp, row in history.iterrows():
                    open_price, high, low, close = (
                        float(row[column])
                        for column in ("Open", "High", "Low", "Close")
                    )
                    volume = float(row["Volume"])
                    if not volume.is_integer() or volume < 0:
                        raise ValueError("Daily candle volume must be a non-negative integer.")
                    if not all(
                        math.isfinite(value)
                        for value in (open_price, high, low, close)
                    ):
                        raise ValueError("Daily candle contains non-finite OHLC data.")
                    candle = OHLCVCandle(
                        timestamp=timestamp.to_pydatetime(),
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=int(volume),
                    )
                    market_date = candle.timestamp.astimezone(MARKET_TIMEZONE).date()
                    if start_date <= market_date <= end_date:
                        candles.append(candle)
            except (AttributeError, OverflowError, TypeError, ValueError) as error:
                raise ProviderUnavailable(
                    "Yahoo Finance returned invalid daily OHLCV values."
                ) from error

        with self._lock:
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic(), candles)
        return candles


@lru_cache(maxsize=1)
def get_market_data_provider() -> MarketDataProvider:
    provider = os.getenv("MARKET_DATA_PROVIDER", "demo").strip().lower()
    if provider == "csv":
        directory = os.getenv("MARKET_DATA_CSV_DIR", "").strip()
        if directory:
            return UserCSVProvider(directory)
    if provider == "finnhub":
        api_key = os.getenv("FINNHUB_API_KEY", "").strip()
        try:
            return FinnhubHistoricalProvider(
                api_key, os.getenv("FINNHUB_SYMBOLS", "")
            )
        except ValueError as error:
            return UnconfiguredProvider(str(error))
    if provider == "yahoo":
        return YahooFinanceHistoricalProvider()
    return UnconfiguredProvider()
