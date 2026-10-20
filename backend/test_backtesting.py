from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.backtesting import StrategyConfig, run_backtest
from backend.market_data import OHLCVCandle


def bars():
    values = [
        (9, 10, 8, 9),
        (9, 11, 8.5, 10),
        (10, 12, 9, 12),
        (12, 14, 11, 12),
        (13, 14, 12, 13),
    ]
    return [
        OHLCVCandle(
            timestamp=datetime(2024, 1, index + 1, tzinfo=timezone.utc),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=1000,
        )
        for index, (open_, high, low, close) in enumerate(values)
    ]


def config(**overrides):
    values = {
        "entry_rule": "range_breakout",
        "breakout_lookback": 2,
        "initial_capital": 10_000,
        "position_size_percent": 50,
        "brokerage_bps": 0,
        "slippage_bps": 0,
        "take_profit_percent": 10,
    }
    values.update(overrides)
    return StrategyConfig(**values)


def test_backtest_executes_breakout_at_next_open_and_tracks_costs():
    result = run_backtest(
        bars(),
        config(
            brokerage_bps=10,
            slippage_bps=10,
        ),
    )
    assert result.data_status == "HISTORICAL"
    assert result.trade_count == 1
    trade = result.trades[0]
    assert trade.entry_at == bars()[3].timestamp
    assert trade.entry_price == pytest.approx(12 * 1.001)
    assert trade.exit_reason == "take_profit"
    assert trade.fees > 0
    assert trade.net_pnl > 0
    assert result.final_capital == pytest.approx(10_000 + trade.net_pnl)
    assert result.equity_curve[-1].equity == pytest.approx(result.final_capital)


def test_stop_loss_wins_when_stop_and_target_are_both_touched():
    result = run_backtest(
        bars(),
        config(stop_loss_percent=5, take_profit_percent=5),
    )
    assert result.trade_count == 1
    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].net_pnl < 0


def test_final_bar_signal_is_not_filled_with_lookahead():
    result = run_backtest(bars()[:3], config())
    assert result.trade_count == 0
    assert result.final_capital == 10_000


def test_backtest_requires_strictly_increasing_candle_times():
    candles = bars()
    candles[2] = candles[1]
    with pytest.raises(ValueError, match="unique, strictly increasing"):
        run_backtest(candles, config())


def test_strategy_rejects_invalid_moving_average_periods():
    with pytest.raises(ValidationError):
        StrategyConfig(fast_period=20, slow_period=10)
