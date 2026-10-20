from datetime import datetime, timezone

import pytest

from backend.portfolio import (
    PortfolioTransactionInput,
    calculate_ledger,
    calculate_portfolio_risk,
)


def transaction(side, quantity, price, fees=0, day=1):
    return PortfolioTransactionInput(
        symbol="SAMPLE",
        exchange="NSE",
        side=side,
        quantity=quantity,
        price=price,
        fees=fees,
        transacted_at=datetime(2024, 1, day, tzinfo=timezone.utc),
    )


def test_weighted_average_cost_realized_profit_and_cash():
    ledger = calculate_ledger(
        1000,
        [
            transaction("BUY", 10, 10, fees=2),
            transaction("BUY", 10, 20, fees=2, day=2),
            transaction("SELL", 5, 30, fees=1, day=3),
        ],
    )
    holding = ledger.holdings["NSE:SAMPLE"]
    assert float(holding.quantity) == 15
    assert float(holding.average_cost) == pytest.approx(15.2)
    assert float(holding.realized_pnl) == pytest.approx(73)
    assert float(ledger.realized_pnl) == pytest.approx(73)
    assert float(ledger.cash_balance) == pytest.approx(845)


def test_ledger_rejects_overselling_and_insufficient_cash():
    with pytest.raises(ValueError, match="exceeds available"):
        calculate_ledger(
            1000,
            [transaction("SELL", 1, 20)],
        )
    with pytest.raises(ValueError, match="Insufficient cash"):
        calculate_ledger(100, [transaction("BUY", 10, 20)])


def test_risk_uses_aligned_daily_returns_and_reports_correlation():
    dates = [
        datetime(2024, 1, day, tzinfo=timezone.utc)
        for day in (1, 2, 3, 4)
    ]
    risk = calculate_portfolio_risk(
        {
            "NSE:A": list(zip(dates, [100, 110, 100, 120])),
            "NSE:B": list(zip(dates, [200, 220, 200, 240])),
        },
        {"NSE:A": 1000, "NSE:B": 1000},
    )
    assert risk.observations == 3
    assert risk.annualized_volatility_percent is not None
    assert risk.maximum_drawdown_percent > 0
    assert risk.correlation["NSE:A"]["NSE:B"] == pytest.approx(1)


def test_risk_reports_insufficient_overlap_without_fabricating_metrics():
    risk = calculate_portfolio_risk(
        {
            "NSE:A": [
                (datetime(2024, 1, 1, tzinfo=timezone.utc), 10),
                (datetime(2024, 1, 2, tzinfo=timezone.utc), 11),
            ],
            "NSE:B": [
                (datetime(2024, 1, 3, tzinfo=timezone.utc), 20),
                (datetime(2024, 1, 4, tzinfo=timezone.utc), 21),
            ],
        },
        {"NSE:A": 100, "NSE:B": 100},
    )
    assert risk.observations == 0
    assert risk.annualized_volatility_percent is None
    assert risk.maximum_drawdown_percent is None
