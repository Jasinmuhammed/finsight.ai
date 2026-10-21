from datetime import datetime, timezone

from backend.risk_meter import (
    RiskMeterPortfolioContext,
    build_risk_meter,
)


AS_OF = datetime(2026, 10, 20, tzinfo=timezone.utc)


def build(**overrides):
    values = {
        "symbol": "SAMPLE",
        "exchange": "NSE",
        "period": "3M",
        "latest_close": 120.0,
        "indicators": {
            "sma_20": 100.0,
            "ema_20": 105.0,
            "rsi_14": 65.0,
            "macd": 2.0,
            "macd_signal": 1.0,
        },
        "period_return_percent": 10.0,
        "annualized_volatility_percent": 15.0,
        "daily_return_observations": 20,
        "source": "Verified test historical source",
        "data_as_of": AS_OF,
        "freshness_status": "RECENT_HISTORY",
        "candle_count": 21,
        "portfolio_context": None,
    }
    values.update(overrides)
    return build_risk_meter(**values)


def test_bullish_inputs_reach_buy_threshold_with_high_confidence():
    assessment = build()

    assert assessment.score == 100
    assert assessment.recommendation == "BUY"
    assert assessment.confidence_percent == 100
    assert assessment.confidence_level == "HIGH"
    assert assessment.risk_level == "LOW"
    assert assessment.data_as_of == AS_OF
    assert assessment.source == "Verified test historical source"
    assert len(assessment.top_factors) == 3
    assert "Close 120.00 is above SMA 20 100.00." in assessment.bullish_evidence
    assert assessment.what_could_change


def test_bearish_and_high_volatility_inputs_reach_sell_threshold():
    assessment = build(
        latest_close=80.0,
        indicators={
            "sma_20": 100.0,
            "ema_20": 95.0,
            "rsi_14": 25.0,
            "macd": -2.0,
            "macd_signal": -1.0,
        },
        period_return_percent=-12.0,
        annualized_volatility_percent=70.0,
    )

    assert assessment.score == 0
    assert assessment.recommendation == "SELL / REDUCE EXPOSURE"
    assert assessment.risk_level == "HIGH"
    assert len(assessment.bearish_evidence) >= 5


def test_mixed_indicators_produce_hold_and_explain_both_sides():
    assessment = build(
        latest_close=101.0,
        indicators={
            "sma_20": 100.0,
            "ema_20": 102.0,
            "rsi_14": 52.0,
            "macd": 0.4,
            "macd_signal": 0.3,
        },
        period_return_percent=-2.0,
        annualized_volatility_percent=30.0,
    )

    assert assessment.score == 61
    assert assessment.recommendation == "HOLD"
    assert assessment.bullish_evidence
    assert assessment.bearish_evidence


def test_stale_or_unknown_history_suppresses_recommendation():
    stale = build(freshness_status="STALE_HISTORY")
    unknown = build(freshness_status="UNKNOWN")

    assert stale.score == 100
    assert stale.status == "STALE_HISTORY"
    assert stale.recommendation == "NOT AVAILABLE"
    assert unknown.status == "UNKNOWN_FRESHNESS"
    assert unknown.recommendation == "NOT AVAILABLE"


def test_missing_core_values_reduce_confidence_and_suppress_score():
    assessment = build(
        indicators={
            "sma_20": None,
            "ema_20": None,
            "rsi_14": 51.0,
            "macd": None,
            "macd_signal": None,
        },
        period_return_percent=0.5,
    )

    assert assessment.score is None
    assert assessment.status == "INSUFFICIENT_DATA"
    assert assessment.recommendation == "NOT AVAILABLE"
    assert assessment.confidence_percent < 60


def test_portfolio_concentration_lowers_score_and_raises_risk_profile():
    baseline = build()
    concentrated = build(
        portfolio_context=RiskMeterPortfolioContext(
            portfolio_name="Core",
            allocation_percent=60,
            annualized_volatility_percent=45,
            maximum_drawdown_percent=20,
            data_as_of=AS_OF,
        )
    )

    assert concentrated.score == baseline.score - 19
    assert concentrated.risk_level == "HIGH"
    assert concentrated.portfolio_context is not None
    assert concentrated.values.portfolio_allocation_percent == 60
    assert any(factor.key == "concentration" and factor.contribution == -12 for factor in concentrated.factors)


def test_risk_profiles_cover_low_moderate_high_and_unknown():
    low = build(annualized_volatility_percent=10)
    moderate = build(annualized_volatility_percent=25)
    high = build(annualized_volatility_percent=45)
    unknown = build(annualized_volatility_percent=None)

    assert low.risk_level == "LOW"
    assert moderate.risk_level == "MODERATE"
    assert high.risk_level == "HIGH"
    assert unknown.risk_level == "UNKNOWN"
