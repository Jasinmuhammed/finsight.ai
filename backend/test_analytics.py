from datetime import datetime, timezone

import pytest

from backend.analytics import (
    calculate_historical_performance,
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


def test_wilder_rsi_matches_a_mixed_gain_loss_reference_series():
    result = rsi([10, 12, 11, 14, 13, 15], 3)
    assert result[:3] == [None, None, None]
    assert result[3:] == pytest.approx([83.3333333333, 66.6666666667, 79.1666666667])


def test_relative_volume_excludes_current_bar_from_baseline():
    assert relative_volume([10, 10, 20], 2) == [None, None, 2.0]


def test_macd_warms_up_before_signal_and_histogram():
    line, signal, histogram = macd(list(range(1, 8)), fast_period=2, slow_period=3, signal_period=2)
    assert line[:2] == [None, None]
    assert signal[:3] == [None, None, None]
    assert line[2] == 0.5
    assert signal[3] == 0.5
    assert histogram[3] == 0.0


def test_macd_line_signal_and_histogram_match_seeded_ema_reference():
    line, signal, histogram = macd(
        [3, 4, 2, 5, 6], fast_period=2, slow_period=3, signal_period=2
    )
    assert line[:2] == [None, None]
    assert line[2:] == pytest.approx([-0.5, 1 / 6, 7 / 18])
    assert signal[:3] == [None, None, None]
    assert signal[3:] == pytest.approx([-1 / 6, 11 / 54])
    assert histogram[:3] == [None, None, None]
    assert histogram[3:] == pytest.approx([1 / 3, 5 / 27])


def test_historical_performance_uses_close_returns_and_sample_volatility():
    candles = [
        candle(1, 100, 100, 100, 100, 10),
        candle(2, 110, 110, 110, 110, 10),
        candle(3, 99, 99, 99, 99, 10),
    ]

    performance = calculate_historical_performance(candles)

    assert performance.period_return_percent == pytest.approx(-1)
    assert performance.annualized_volatility_percent == pytest.approx(
        0.2 * (2**0.5) / 2 * (252**0.5) * 100
    )
    assert performance.daily_return_observations == 2
    assert "252 trading days" in performance.method


def test_historical_performance_uses_available_bars_without_filling_missing_sessions():
    candles = [
        candle(1, 100, 100, 100, 100, 10),
        candle(5, 110, 110, 110, 110, 10),
        candle(20, 99, 99, 99, 99, 10),
    ]

    performance = calculate_historical_performance(candles)

    assert performance.period_return_percent == pytest.approx(-1)
    assert performance.daily_return_observations == 2
    assert performance.annualized_volatility_percent == pytest.approx(
        0.2 * (2**0.5) / 2 * (252**0.5) * 100
    )


def test_historical_performance_handles_empty_and_insufficient_history():
    assert calculate_historical_performance([]).model_dump() == {
        "period_return_percent": None,
        "annualized_volatility_percent": None,
        "daily_return_observations": 0,
        "method": (
            "Close-to-close simple returns; annualized sample standard deviation "
            "of daily returns uses 252 trading days."
        ),
    }
    one_candle = calculate_historical_performance(
        [candle(1, 100, 100, 100, 100, 10)]
    )
    assert one_candle.period_return_percent is None
    assert one_candle.annualized_volatility_percent is None

    two_candles = calculate_historical_performance(
        [candle(1, 100, 100, 100, 100, 10), candle(2, 110, 110, 110, 110, 10)]
    )
    assert two_candles.period_return_percent == pytest.approx(10)
    assert two_candles.annualized_volatility_percent is None


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
