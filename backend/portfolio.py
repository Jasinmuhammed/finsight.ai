from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import re
from statistics import correlation, stdev
from math import sqrt
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PortfolioTransactionInput(BaseModel):
    symbol: str
    exchange: Literal["NSE", "BSE"]
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0, allow_inf_nan=False)
    price: float = Field(gt=0, allow_inf_nan=False)
    fees: float = Field(default=0, ge=0, allow_inf_nan=False)
    transacted_at: datetime

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,31}", normalized):
            raise ValueError("symbol must use letters, digits, dot, underscore, or hyphen")
        return normalized

    @field_validator("transacted_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transacted_at must include a timezone")
        return value.astimezone(timezone.utc)


@dataclass
class HoldingState:
    quantity: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    @property
    def average_cost(self) -> Decimal:
        if self.quantity == 0:
            return Decimal("0")
        return self.cost_basis / self.quantity


@dataclass
class PortfolioLedger:
    cash_balance: Decimal
    holdings: dict[str, HoldingState] = field(default_factory=dict)
    realized_pnl: Decimal = Decimal("0")


def calculate_ledger(
    initial_cash: float, transactions: list[PortfolioTransactionInput]
) -> PortfolioLedger:
    cash = Decimal(str(initial_cash))
    ledger = PortfolioLedger(cash_balance=cash)
    ordered = sorted(
        transactions,
        key=lambda transaction: transaction.transacted_at.astimezone(timezone.utc),
    )
    for transaction in ordered:
        if transaction.side not in {"BUY", "SELL"}:
            raise ValueError("Transaction side must be BUY or SELL.")
        symbol = f"{transaction.exchange.upper()}:{transaction.symbol.upper()}"
        quantity = Decimal(str(transaction.quantity))
        price = Decimal(str(transaction.price))
        fees = Decimal(str(transaction.fees))
        gross = quantity * price
        holding = ledger.holdings.setdefault(symbol, HoldingState())

        if transaction.side == "BUY":
            total_cost = gross + fees
            if total_cost > ledger.cash_balance:
                raise ValueError(
                    f"Insufficient cash for {symbol} purchase including fees."
                )
            ledger.cash_balance -= total_cost
            holding.quantity += quantity
            holding.cost_basis += total_cost
        else:
            if quantity > holding.quantity:
                raise ValueError(f"Sell quantity exceeds available {symbol} holdings.")
            average_cost = holding.average_cost
            realized = (price - average_cost) * quantity - fees
            ledger.cash_balance += gross - fees
            holding.quantity -= quantity
            holding.cost_basis -= average_cost * quantity
            holding.realized_pnl += realized
            ledger.realized_pnl += realized
            if holding.quantity == 0:
                holding.cost_basis = Decimal("0")

    return ledger


class PortfolioRisk(BaseModel):
    observations: int
    annualized_volatility_percent: float | None
    maximum_drawdown_percent: float | None
    correlation: dict[str, dict[str, float | None]]
    assumptions: list[str]


def calculate_portfolio_risk(
    price_history: dict[str, list[tuple[datetime, float]]],
    market_value_weights: dict[str, float],
) -> PortfolioRisk:
    returns_by_symbol: dict[str, dict[date, float]] = {}
    for symbol, observations in price_history.items():
        ordered = sorted(observations, key=lambda item: item[0])
        if any(price <= 0 for _, price in ordered):
            raise ValueError("Historical prices must be positive to calculate returns.")
        returns_by_symbol[symbol] = {
            ordered[index][0].date(): ordered[index][1] / ordered[index - 1][1] - 1
            for index in range(1, len(ordered))
            if ordered[index - 1][1] > 0
        }

    symbols = [
        symbol
        for symbol, weight in market_value_weights.items()
        if weight > 0 and symbol in returns_by_symbol and returns_by_symbol[symbol]
    ]
    common_dates: set[date] = (
        set.intersection(*(set(returns_by_symbol[symbol]) for symbol in symbols))
        if symbols
        else set()
    )
    aligned_dates = sorted(common_dates)
    if len(aligned_dates) < 2:
        return PortfolioRisk(
            observations=len(aligned_dates),
            annualized_volatility_percent=None,
            maximum_drawdown_percent=None,
            correlation={},
            assumptions=[
                "At least two aligned daily return observations are required.",
                "Historical risk measures do not guarantee future outcomes.",
            ],
        )

    total_weight = sum(market_value_weights[symbol] for symbol in symbols)
    normalized_weights = {
        symbol: market_value_weights[symbol] / total_weight for symbol in symbols
    }
    aligned_returns = {
        symbol: [returns_by_symbol[symbol][day] for day in aligned_dates]
        for symbol in symbols
    }
    portfolio_returns = [
        sum(
            normalized_weights[symbol] * aligned_returns[symbol][index]
            for symbol in symbols
        )
        for index in range(len(aligned_dates))
    ]
    volatility = stdev(portfolio_returns) * sqrt(252) * 100
    wealth = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for daily_return in portfolio_returns:
        wealth *= 1 + daily_return
        peak = max(peak, wealth)
        maximum_drawdown = min(maximum_drawdown, (wealth / peak - 1) * 100)

    correlations: dict[str, dict[str, float | None]] = {}
    for left in symbols:
        correlations[left] = {}
        for right in symbols:
            if left == right:
                correlations[left][right] = 1.0
            else:
                left_values = aligned_returns[left]
                right_values = aligned_returns[right]
                if stdev(left_values) == 0 or stdev(right_values) == 0:
                    correlations[left][right] = None
                else:
                    correlations[left][right] = correlation(left_values, right_values)

    return PortfolioRisk(
        observations=len(aligned_dates),
        annualized_volatility_percent=volatility,
        maximum_drawdown_percent=abs(maximum_drawdown),
        correlation=correlations,
        assumptions=[
            "Daily close-to-close arithmetic returns use dates present for every included holding.",
            "Portfolio weights use the latest available historical market values and are held constant over the aligned return window.",
            "Annualized volatility uses sample standard deviation multiplied by the square root of 252 trading days.",
            "Historical volatility, drawdown, and correlation are not forecasts.",
            "Corporate actions, dividends, taxes, and missing sessions are not adjusted by this CSV provider.",
        ],
    )
