from datetime import datetime
from math import sqrt
from statistics import fmean, stdev
from typing import Literal

from pydantic import BaseModel

from backend.market_data import OHLCVCandle

NumericSeries = list[float | None]


class PatternCondition(BaseModel):
    rule: str
    passed: bool
    observed: float | None
    threshold: float | None


class PatternDetection(BaseModel):
    name: Literal["Historical range breakout"]
    detection_time: datetime
    timeframe: Literal["1d"]
    lookback_bars: int
    conditions: list[PatternCondition]
    prior_range_high: float
    relative_volume: float | None
    explanation: str
    limitations: list[str]


class HistoricalPerformance(BaseModel):
    period_return_percent: float | None
    annualized_volatility_percent: float | None
    daily_return_observations: int
    method: str


def _validate_period(period: int) -> None:
    if period < 1:
        raise ValueError("period must be at least 1")


def sma(values: list[float], period: int) -> NumericSeries:
    _validate_period(period)
    result: NumericSeries = [None] * len(values)
    rolling_total = 0.0
    for index, value in enumerate(values):
        rolling_total += value
        if index >= period:
            rolling_total -= values[index - period]
        if index >= period - 1:
            result[index] = rolling_total / period
    return result


def calculate_historical_performance(
    candles: list[OHLCVCandle],
) -> HistoricalPerformance:
    closes = [candle.close for candle in candles]
    period_return = (
        (closes[-1] / closes[0] - 1) * 100 if len(closes) >= 2 else None
    )
    daily_returns = [
        current / previous - 1
        for previous, current in zip(closes, closes[1:])
    ]
    annualized_volatility = (
        stdev(daily_returns) * sqrt(252) * 100
        if len(daily_returns) >= 2
        else None
    )
    return HistoricalPerformance(
        period_return_percent=period_return,
        annualized_volatility_percent=annualized_volatility,
        daily_return_observations=len(daily_returns),
        method=(
            "Close-to-close simple returns; annualized sample standard deviation "
            "of daily returns uses 252 trading days."
        ),
    )


def ema(values: list[float], period: int) -> NumericSeries:
    _validate_period(period)
    result: NumericSeries = [None] * len(values)
    if len(values) < period:
        return result
    current = fmean(values[:period])
    result[period - 1] = current
    multiplier = 2 / (period + 1)
    for index in range(period, len(values)):
        current = (values[index] - current) * multiplier + current
        result[index] = current
    return result


def rsi(values: list[float], period: int = 14) -> NumericSeries:
    _validate_period(period)
    result: NumericSeries = [None] * len(values)
    if len(values) <= period:
        return result

    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    average_gain = fmean(max(change, 0.0) for change in changes[:period])
    average_loss = fmean(max(-change, 0.0) for change in changes[:period])

    def value_for(gain: float, loss: float) -> float:
        if gain == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        relative_strength = gain / loss
        return 100 - 100 / (1 + relative_strength)

    result[period] = value_for(average_gain, average_loss)
    for index in range(period + 1, len(values)):
        change = changes[index - 1]
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
        result[index] = value_for(average_gain, average_loss)
    return result


def macd(
    values: list[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> tuple[NumericSeries, NumericSeries, NumericSeries]:
    _validate_period(fast_period)
    _validate_period(slow_period)
    _validate_period(signal_period)
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")
    fast = ema(values, fast_period)
    slow = ema(values, slow_period)
    line: NumericSeries = [
        fast_value - slow_value
        if fast_value is not None and slow_value is not None
        else None
        for fast_value, slow_value in zip(fast, slow)
    ]
    first_valid = next((index for index, value in enumerate(line) if value is not None), None)
    signal: NumericSeries = [None] * len(values)
    histogram: NumericSeries = [None] * len(values)
    if first_valid is None:
        return line, signal, histogram

    macd_values = [value for value in line[first_valid:] if value is not None]
    signal_values = ema(macd_values, signal_period)
    for offset, signal_value in enumerate(signal_values):
        index = first_valid + offset
        signal[index] = signal_value
        if signal_value is not None:
            histogram[index] = line[index] - signal_value
    return line, signal, histogram


def relative_volume(volumes: list[int], lookback: int = 20) -> NumericSeries:
    _validate_period(lookback)
    result: NumericSeries = [None] * len(volumes)
    for index in range(lookback, len(volumes)):
        baseline = fmean(volumes[index - lookback : index])
        result[index] = volumes[index] / baseline if baseline > 0 else None
    return result


def calculate_indicators(
    candles: list[OHLCVCandle],
    sma_period: int = 20,
    ema_period: int = 20,
    rsi_period: int = 14,
) -> dict[str, NumericSeries]:
    closes = [candle.close for candle in candles]
    macd_line, macd_signal, macd_histogram = macd(closes)
    return {
        "sma": sma(closes, sma_period),
        "ema": ema(closes, ema_period),
        "rsi": rsi(closes, rsi_period),
        "relative_volume": relative_volume([candle.volume for candle in candles], 20),
        "macd": macd_line,
        "macd_signal": macd_signal,
        "macd_histogram": macd_histogram,
    }


def detect_range_breakouts(
    candles: list[OHLCVCandle],
    lookback: int = 20,
    volume_multiplier: float = 1.5,
) -> list[PatternDetection]:
    _validate_period(lookback)
    if volume_multiplier <= 0:
        raise ValueError("volume_multiplier must be greater than zero")
    detections = []
    for index in range(lookback, len(candles)):
        current = candles[index]
        prior = candles[index - lookback : index]
        prior_high = max(candle.high for candle in prior)
        if current.close <= prior_high:
            continue
        baseline_volume = fmean(candle.volume for candle in prior)
        relative_vol = current.volume / baseline_volume if baseline_volume > 0 else None
        volume_confirmed = (
            relative_vol is not None and relative_vol >= volume_multiplier
        )
        detections.append(
            PatternDetection(
                name="Historical range breakout",
                detection_time=current.timestamp,
                timeframe="1d",
                lookback_bars=lookback,
                conditions=[
                    PatternCondition(
                        rule="Close exceeds the prior lookback high",
                        passed=True,
                        observed=current.close,
                        threshold=prior_high,
                    ),
                    PatternCondition(
                        rule="Volume is at least the configured multiple of prior average",
                        passed=volume_confirmed,
                        observed=relative_vol,
                        threshold=volume_multiplier,
                    ),
                ],
                prior_range_high=prior_high,
                relative_volume=relative_vol,
                explanation=(
                    "The completed daily close exceeded the high of the preceding "
                    f"{lookback} candles. Relative volume is "
                    f"{relative_vol:.2f}x the prior average."
                    if relative_vol is not None
                    else "The completed daily close exceeded the prior range high; "
                    "volume confirmation is unavailable."
                ),
                limitations=[
                    "A historical pattern is not a prediction or a profitability claim.",
                    "Daily candles do not establish intraday signal timing.",
                    "The rule uses only candles through the detection close; later candles are excluded.",
                ],
            )
        )
    return detections
