from datetime import datetime
from math import floor, sqrt
from statistics import mean, stdev
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.analytics import ema, sma
from backend.market_data import OHLCVCandle

BARS_PER_YEAR = 252


class StrategyConfig(BaseModel):
    entry_rule: Literal["sma_crossover", "range_breakout"] = "sma_crossover"
    fast_period: int = Field(default=10, ge=2, le=252)
    slow_period: int = Field(default=20, ge=3, le=504)
    breakout_lookback: int = Field(default=20, ge=2, le=252)
    initial_capital: float = Field(default=100_000, gt=0, allow_inf_nan=False)
    position_size_percent: float = Field(default=100, gt=0, le=100, allow_inf_nan=False)
    brokerage_bps: float = Field(default=10, ge=0, le=5000, allow_inf_nan=False)
    slippage_bps: float = Field(default=10, ge=0, le=5000, allow_inf_nan=False)
    stop_loss_percent: float | None = Field(
        default=None, gt=0, lt=100, allow_inf_nan=False
    )
    take_profit_percent: float | None = Field(
        default=None, gt=0, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def validate_periods(self) -> "StrategyConfig":
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")
        if self.take_profit_percent is not None and self.take_profit_percent > 1000:
            raise ValueError("take_profit_percent must be at most 1000")
        return self


class BacktestTrade(BaseModel):
    entry_at: datetime
    exit_at: datetime
    quantity: int
    entry_price: float
    exit_price: float
    fees: float
    net_pnl: float
    return_percent: float
    exit_reason: Literal["opposite_signal", "stop_loss", "take_profit", "end_of_data"]


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float
    drawdown_percent: float


class BacktestResult(BaseModel):
    initial_capital: float
    final_capital: float
    net_profit: float
    total_return_percent: float
    annualized_return_percent: float | None
    maximum_drawdown_percent: float
    win_rate_percent: float
    trade_count: int
    average_win: float | None
    average_loss: float | None
    profit_factor: float | None
    sharpe_ratio: float | None
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    assumptions: list[str]
    data_status: Literal["HISTORICAL"]


class _Position:
    def __init__(
        self,
        quantity: int,
        entry_at: datetime,
        entry_price: float,
        entry_fee: float,
    ) -> None:
        self.quantity = quantity
        self.entry_at = entry_at
        self.entry_price = entry_price
        self.entry_fee = entry_fee
        self.entry_cost = quantity * entry_price + entry_fee


def _signals(
    candles: list[OHLCVCandle], config: StrategyConfig
) -> tuple[list[bool], list[bool]]:
    closes = [candle.close for candle in candles]
    entries = [False] * len(candles)
    exits = [False] * len(candles)
    if config.entry_rule == "sma_crossover":
        fast = sma(closes, config.fast_period)
        slow = sma(closes, config.slow_period)
        for index in range(1, len(candles)):
            if fast[index - 1] is None or slow[index - 1] is None:
                continue
            if fast[index] is None or slow[index] is None:
                continue
            entries[index] = fast[index - 1] <= slow[index - 1] and fast[index] > slow[index]
            exits[index] = fast[index - 1] >= slow[index - 1] and fast[index] < slow[index]
    else:
        exit_average = sma(closes, config.slow_period)
        for index in range(config.breakout_lookback, len(candles)):
            prior_high = max(
                candle.high
                for candle in candles[index - config.breakout_lookback : index]
            )
            entries[index] = candles[index].close > prior_high
            average = exit_average[index]
            exits[index] = average is not None and candles[index].close < average
    return entries, exits


def _buy_fill(open_price: float, slippage: float) -> float:
    return open_price * (1 + slippage)


def _sell_fill(price: float, slippage: float) -> float:
    return price * (1 - slippage)


def run_backtest(
    candles: list[OHLCVCandle], config: StrategyConfig
) -> BacktestResult:
    if len(candles) < 2:
        raise ValueError("At least two daily candles are required.")
    if any(
        current.timestamp <= previous.timestamp
        for previous, current in zip(candles, candles[1:])
    ):
        raise ValueError("Candles must have unique, strictly increasing timestamps.")

    entries, exits = _signals(candles, config)
    fee_rate = config.brokerage_bps / 10_000
    slippage = config.slippage_bps / 10_000
    cash = config.initial_capital
    position: _Position | None = None
    trades: list[BacktestTrade] = []
    equity_values: list[tuple[datetime, float]] = []
    previous_exit_reason: BacktestTrade.exit_reason | None = None

    def close_position(
        candle: OHLCVCandle,
        base_price: float,
        reason: BacktestTrade.exit_reason,
    ) -> None:
        nonlocal cash, position
        if position is None:
            return
        exit_price = _sell_fill(base_price, slippage)
        exit_notional = position.quantity * exit_price
        exit_fee = exit_notional * fee_rate
        cash += exit_notional - exit_fee
        total_fees = position.entry_fee + exit_fee
        net_pnl = exit_notional - exit_fee - position.entry_cost
        trades.append(
            BacktestTrade(
                entry_at=position.entry_at,
                exit_at=candle.timestamp,
                quantity=position.quantity,
                entry_price=position.entry_price,
                exit_price=exit_price,
                fees=total_fees,
                net_pnl=net_pnl,
                return_percent=net_pnl / position.entry_cost * 100,
                exit_reason=reason,
            )
        )
        position = None

    for index, candle in enumerate(candles):
        closed_at_open = False
        if position and index > 0 and exits[index - 1]:
            close_position(candle, candle.open, "opposite_signal")
            closed_at_open = True

        if position is None and not closed_at_open and index > 0 and entries[index - 1]:
            fill = _buy_fill(candle.open, slippage)
            allocated = min(
                cash, config.initial_capital * config.position_size_percent / 100
            )
            quantity = floor(allocated / (fill * (1 + fee_rate)))
            if quantity > 0:
                entry_fee = quantity * fill * fee_rate
                cash -= quantity * fill + entry_fee
                position = _Position(quantity, candle.timestamp, fill, entry_fee)

        if position:
            stop_price = (
                position.entry_price * (1 - config.stop_loss_percent / 100)
                if config.stop_loss_percent is not None
                else None
            )
            target_price = (
                position.entry_price * (1 + config.take_profit_percent / 100)
                if config.take_profit_percent is not None
                else None
            )
            if stop_price is not None and candle.open <= stop_price:
                close_position(candle, candle.open, "stop_loss")
            elif stop_price is not None and candle.low <= stop_price:
                close_position(candle, stop_price, "stop_loss")
            elif target_price is not None and candle.open >= target_price:
                close_position(candle, candle.open, "take_profit")
            elif target_price is not None and candle.high >= target_price:
                close_position(candle, target_price, "take_profit")

        if position and index == len(candles) - 1:
            close_position(candle, candle.close, "end_of_data")

        equity = cash + (position.quantity * candle.close if position else 0)
        equity_values.append((candle.timestamp, equity))

    peak = config.initial_capital
    equity_curve = []
    drawdowns = []
    for timestamp, equity in equity_values:
        peak = max(peak, equity)
        drawdown = (equity / peak - 1) * 100 if peak else 0
        drawdowns.append(drawdown)
        equity_curve.append(
            EquityPoint(timestamp=timestamp, equity=equity, drawdown_percent=drawdown)
        )

    final_capital = cash
    net_profit = final_capital - config.initial_capital
    wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    daily_returns = [
        current / previous - 1
        for previous, current in zip(
            [config.initial_capital, *(value for _, value in equity_values[:-1])],
            [value for _, value in equity_values],
        )
        if previous > 0
    ]
    sharpe = None
    if len(daily_returns) > 1 and stdev(daily_returns) > 0:
        sharpe = mean(daily_returns) / stdev(daily_returns) * sqrt(BARS_PER_YEAR)

    elapsed_days = (candles[-1].timestamp - candles[0].timestamp).total_seconds() / 86400
    annualized_return = None
    if elapsed_days >= 365 and final_capital > 0:
        annualized_return = (
            (final_capital / config.initial_capital) ** (365.25 / elapsed_days) - 1
        ) * 100

    return BacktestResult(
        initial_capital=config.initial_capital,
        final_capital=final_capital,
        net_profit=net_profit,
        total_return_percent=net_profit / config.initial_capital * 100,
        annualized_return_percent=annualized_return,
        maximum_drawdown_percent=abs(min(drawdowns, default=0)),
        win_rate_percent=(len(wins) / len(trades) * 100) if trades else 0,
        trade_count=len(trades),
        average_win=mean(wins) if wins else None,
        average_loss=mean(losses) if losses else None,
        profit_factor=(gross_profit / gross_loss) if gross_loss else None,
        sharpe_ratio=sharpe,
        trades=trades,
        equity_curve=equity_curve,
        assumptions=[
            "Signals are evaluated after each daily close and execute at the next daily open.",
            "SMA crossover exits on a bearish crossover; range-breakout exits when the close falls below the configured slow SMA.",
            "Stop-loss fills use the opening price when the market gaps through the stop; otherwise the stop price is used.",
            "If both stop-loss and take-profit levels are crossed in one candle, the stop-loss is applied first.",
            "Brokerage is charged in basis points on each side; slippage is applied to entry and exit fills.",
            "Remaining positions are liquidated at the final available close.",
            "No taxes, dividends, corporate actions, market impact, or survivorship adjustment are modeled.",
            "Results are historical simulations and do not predict future performance.",
        ],
        data_status="HISTORICAL",
    )
