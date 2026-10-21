from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.analytics import ema, relative_volume, rsi, sma
from backend.market_data import MarketDataProvider, historical_freshness


class AdvancedScreenerRequest(BaseModel):
    exchange: Literal["NSE", "BSE"] | None = None
    min_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    min_change_percent: float | None = Field(default=None, allow_inf_nan=False)
    max_change_percent: float | None = Field(default=None, allow_inf_nan=False)
    min_volume: int | None = Field(default=None, ge=0)
    min_relative_volume: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_relative_volume: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    min_rsi: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    max_rsi: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    price_above_sma: int | None = Field(default=None, ge=2, le=252)
    price_above_ema: int | None = Field(default=None, ge=2, le=252)
    breakout_lookback: int | None = Field(default=None, ge=2, le=252)
    combine: Literal["AND", "OR"] = "AND"
    sort_by: Literal["symbol", "price", "change_percent", "volume", "relative_volume", "rsi"] = "symbol"
    sort_order: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_ranges(self) -> "AdvancedScreenerRequest":
        pairs = (
            (self.min_price, self.max_price, "price"),
            (self.min_change_percent, self.max_change_percent, "change"),
            (self.min_rsi, self.max_rsi, "RSI"),
            (self.min_relative_volume, self.max_relative_volume, "relative volume"),
        )
        for minimum, maximum, label in pairs:
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"minimum {label} must be less than or equal to maximum {label}")
        return self


class ScreenerMatch(BaseModel):
    symbol: str
    name: str
    exchange: Literal["NSE", "BSE"]
    last_price: float
    change_percent: float | None
    volume: int
    relative_volume: float | None
    rsi: float | None
    sma: float | None
    ema: float | None
    matched_conditions: list[str]
    data_as_of: datetime
    freshness_status: Literal["RECENT_HISTORY", "STALE_HISTORY", "UNKNOWN"]


class AdvancedScreenerResponse(BaseModel):
    results: list[ScreenerMatch]
    count: int
    limit: int
    offset: int
    data_status: Literal["HISTORICAL"]
    source: str
    data_as_of: datetime | None
    freshness_status: Literal[
        "RECENT_HISTORY", "STALE_HISTORY", "MIXED_HISTORY", "UNKNOWN"
    ]


def screen_historical_instruments(
    provider: MarketDataProvider, filters: AdvancedScreenerRequest
) -> AdvancedScreenerResponse:
    instruments = provider.search_instruments("", limit=200)
    if filters.exchange:
        instruments = [
            instrument for instrument in instruments if instrument.exchange == filters.exchange
        ]

    matches: list[ScreenerMatch] = []
    predicate_count = sum(
        value is not None
        for value in (
            filters.min_price,
            filters.max_price,
            filters.min_change_percent,
            filters.max_change_percent,
            filters.min_volume,
            filters.min_relative_volume,
            filters.max_relative_volume,
            filters.min_rsi,
            filters.max_rsi,
            filters.price_above_sma,
            filters.price_above_ema,
            filters.breakout_lookback,
        )
    )
    for instrument in instruments:
        candles = provider.historical_daily_candles(
            instrument.symbol, instrument.exchange, None, None
        )
        if not candles:
            continue
        closes = [candle.close for candle in candles]
        volumes = [candle.volume for candle in candles]
        price = closes[-1]
        change = (
            (price / closes[-2] - 1) * 100
            if len(closes) > 1 and closes[-2] != 0
            else None
        )
        rvol_series = relative_volume(volumes, 20)
        rsi_series = rsi(closes, 14)
        sma_series = sma(closes, 20)
        ema_series = ema(closes, 20)
        current_rvol = rvol_series[-1]
        current_rsi = rsi_series[-1]
        current_sma = sma_series[-1]
        current_ema = ema_series[-1]
        conditions: list[tuple[str, bool]] = []

        def compare(label: str, value: float | int | None, operation: str, threshold: float | int) -> None:
            available = value is not None
            if operation == "min":
                passed = available and value >= threshold
                description = f"{label} >= {threshold}"
            else:
                passed = available and value <= threshold
                description = f"{label} <= {threshold}"
            conditions.append((description, bool(passed)))

        if filters.min_price is not None:
            compare("Price", price, "min", filters.min_price)
        if filters.max_price is not None:
            compare("Price", price, "max", filters.max_price)
        if filters.min_change_percent is not None:
            compare("Change %", change, "min", filters.min_change_percent)
        if filters.max_change_percent is not None:
            compare("Change %", change, "max", filters.max_change_percent)
        if filters.min_volume is not None:
            compare("Volume", volumes[-1], "min", filters.min_volume)
        if filters.min_relative_volume is not None:
            compare("Relative volume", current_rvol, "min", filters.min_relative_volume)
        if filters.max_relative_volume is not None:
            compare("Relative volume", current_rvol, "max", filters.max_relative_volume)
        if filters.min_rsi is not None:
            compare("RSI", current_rsi, "min", filters.min_rsi)
        if filters.max_rsi is not None:
            compare("RSI", current_rsi, "max", filters.max_rsi)
        if filters.price_above_sma is not None:
            average = sma(closes, filters.price_above_sma)[-1]
            conditions.append(
                (f"Price above SMA({filters.price_above_sma})", average is not None and price > average)
            )
        if filters.price_above_ema is not None:
            average = ema(closes, filters.price_above_ema)[-1]
            conditions.append(
                (f"Price above EMA({filters.price_above_ema})", average is not None and price > average)
            )
        if filters.breakout_lookback is not None:
            lookback = filters.breakout_lookback
            previous_high = (
                max(candle.high for candle in candles[-lookback - 1 : -1])
                if len(candles) > lookback
                else None
            )
            conditions.append(
                (
                    f"Close above previous {lookback}-bar high",
                    previous_high is not None and price > previous_high,
                )
            )

        passed_conditions = [label for label, passed in conditions if passed]
        matched = (
            all(passed for _, passed in conditions)
            if filters.combine == "AND"
            else any(passed for _, passed in conditions)
        )
        if predicate_count == 0 or matched:
            matches.append(
                ScreenerMatch(
                    symbol=instrument.symbol,
                    name=instrument.name,
                    exchange=instrument.exchange,
                    last_price=price,
                    change_percent=change,
                    volume=volumes[-1],
                    relative_volume=current_rvol,
                    rsi=current_rsi,
                    sma=current_sma,
                    ema=current_ema,
                    matched_conditions=passed_conditions,
                    data_as_of=candles[-1].timestamp,
                    freshness_status=historical_freshness(candles[-1].timestamp),
                )
            )

    sort_field = filters.sort_by
    if sort_field == "symbol":
        matches.sort(key=lambda item: item.symbol, reverse=filters.sort_order == "desc")
    else:
        key_name = "last_price" if sort_field == "price" else sort_field
        available = [item for item in matches if getattr(item, key_name) is not None]
        missing = [item for item in matches if getattr(item, key_name) is None]
        available.sort(
            key=lambda item: getattr(item, key_name),
            reverse=filters.sort_order == "desc",
        )
        matches = [*available, *missing]

    data_as_of = max((item.data_as_of for item in matches), default=None)
    freshness_states = {item.freshness_status for item in matches}
    freshness_status = (
        "UNKNOWN"
        if not freshness_states
        else next(iter(freshness_states))
        if len(freshness_states) == 1
        else "MIXED_HISTORY"
    )
    return AdvancedScreenerResponse(
        results=matches[filters.offset : filters.offset + filters.limit],
        count=len(matches),
        limit=filters.limit,
        offset=filters.offset,
        data_status="HISTORICAL",
        source=provider.source_label,
        data_as_of=data_as_of,
        freshness_status=freshness_status,
    )
