from datetime import datetime, timezone

from backend.analytics import (
    detect_range_breakouts,
    ema,
    macd,
    relative_volume,
    rsi,
    sma,
)
from backend.market_data import OHLCVCandle


def candle(day: int, open_: float, high: float, low: float, close: float, volume: int):
    return OHLCVCandle(
        timestamp=datetime(2024, 1, day, tzinfo=timezone.utc),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_sma_and_ema_use_seeded_period_windows():
    assert sma([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]
    assert ema([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_rsi_handles_rising_and_flat_series():
    assert rsi([1, 2, 3], 2) == [None, None, 100.0]
    assert rsi([5, 5, 5], 2) == [None, None, 50.0]


def test_relative_volume_excludes_current_bar_from_baseline():
    assert relative_volume([10, 10, 20], 2) == [None, None, 2.0]


def test_macd_warms_up_before_signal_and_histogram():
    line, signal, histogram = macd(list(range(1, 8)), fast_period=2, slow_period=3, signal_period=2)
    assert line[:2] == [None, None]
    assert signal[:3] == [None, None, None]
    assert line[2] == 0.5
    assert signal[3] == 0.5
    assert histogram[3] == 0.0


def test_breakout_uses_only_prior_candles_and_reports_volume_rule():
    series = [
        candle(1, 8, 10, 7, 9, 100),
        candle(2, 9, 11, 8, 10, 100),
        candle(3, 10, 12, 9, 11, 100),
        candle(4, 12, 14, 11, 13, 200),
    ]
    detection = detect_range_breakouts(series, lookback=3, volume_multiplier=1.5)[0]
    assert detection.prior_range_high == 12
    assert detection.relative_volume == 2
    assert all(condition.passed for condition in detection.conditions)
    assert detection.detection_time == series[3].timestamp

    later = series + [candle(5, 20, 30, 19, 29, 1000)]
    first_detection_after_append = detect_range_breakouts(
        later, lookback=3, volume_multiplier=1.5
    )[0]
    assert first_detection_after_append.prior_range_high == detection.prior_range_high
    assert first_detection_after_append.detection_time == detection.detection_time


def test_breakout_keeps_volume_failure_explainable():
    series = [
        candle(1, 8, 10, 7, 9, 100),
        candle(2, 9, 11, 8, 10, 100),
        candle(3, 10, 12, 9, 11, 100),
        candle(4, 12, 14, 11, 13, 100),
    ]
    detection = detect_range_breakouts(series, lookback=3, volume_multiplier=1.5)[0]
    assert detection.conditions[0].passed
    assert not detection.conditions[1].passed
