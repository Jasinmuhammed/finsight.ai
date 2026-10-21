from datetime import datetime
from math import isfinite
from typing import Literal

from pydantic import BaseModel


Recommendation = Literal["BUY", "HOLD", "SELL / REDUCE EXPOSURE", "NOT AVAILABLE"]
RiskLevel = Literal["LOW", "MODERATE", "HIGH", "UNKNOWN"]
ConfidenceLevel = Literal["LOW", "MODERATE", "HIGH"]
AssessmentStatus = Literal[
    "READY", "INSUFFICIENT_DATA", "STALE_HISTORY", "UNKNOWN_FRESHNESS"
]


class RiskMeterPortfolioContext(BaseModel):
    portfolio_name: str
    allocation_percent: float | None
    annualized_volatility_percent: float | None
    maximum_drawdown_percent: float | None
    data_as_of: datetime | None


class RiskMeterFactor(BaseModel):
    key: str
    title: str
    contribution: int
    evidence: str
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL", "RISK"]


class RiskMeterValues(BaseModel):
    latest_close: float | None
    sma_20: float | None
    ema_20: float | None
    rsi_14: float | None
    macd: float | None
    macd_signal: float | None
    period_return_percent: float | None
    annualized_volatility_percent: float | None
    portfolio_allocation_percent: float | None
    portfolio_annualized_volatility_percent: float | None
    portfolio_maximum_drawdown_percent: float | None


class RiskMeterResponse(BaseModel):
    symbol: str
    exchange: Literal["NSE", "BSE"]
    period: Literal["1M", "3M", "6M", "1Y"]
    status: AssessmentStatus
    score: int | None
    recommendation: Recommendation
    confidence_percent: int
    confidence_level: ConfidenceLevel
    risk_level: RiskLevel
    source: str | None
    data_as_of: datetime | None
    freshness_status: Literal["RECENT_HISTORY", "STALE_HISTORY", "UNKNOWN"] | None
    candle_count: int
    daily_return_observations: int
    values: RiskMeterValues
    factors: list[RiskMeterFactor]
    top_factors: list[RiskMeterFactor]
    bullish_evidence: list[str]
    bearish_evidence: list[str]
    what_could_change: list[str]
    formula: str
    limitations: list[str]
    portfolio_context: RiskMeterPortfolioContext | None
    ai_explanation_status: Literal["NOT_REQUESTED", "NOT_CONFIGURED", "AVAILABLE", "ERROR"]
    ai_explanation: str | None
    ai_explanation_message: str | None


FORMULA = (
    "Start at 50. Add close vs SMA20 (+12/-12), close vs EMA20 (+8/-8), "
    "MACD vs signal (+12/-12), and period return (+10 for >=5%, +5 for >0% "
    "to <5%, 0 at 0%, -5 for <0% to >-5%, -10 for <=-5%). RSI14 contributes "
    "-8 at >=70, +6 at >=60, +3 at >=55, 0 for >45 and <55, -3 for >40 "
    "through 45, -6 for 30 through 40, and -8 below 30. Instrument annualized "
    "volatility contributes -10 above 60%, -5 above 40% through 60%, 0 above "
    "20% through 40%, and +2 at or below 20%. If a portfolio is selected, "
    "portfolio volatility contributes -6 above 60%, -3 above 40% through 60%, "
    "otherwise 0; drawdown contributes -8 above 30%, -4 above 15% through "
    "30%, otherwise 0; holding concentration contributes -12 above 50%, -8 "
    "above 35% through 50%, -4 above 20% through 35%, otherwise 0. Clamp to "
    "0–100. BUY >=65, HOLD 36–64, SELL / REDUCE EXPOSURE <=35. Missing factors "
    "contribute zero but reduce confidence; fewer than three core signals "
    "suppress the score. Confidence is 70% core-signal completeness plus 30% "
    "directional agreement (HIGH >=80, MODERATE >=60, otherwise LOW). Risk is "
    "HIGH at instrument or portfolio volatility >=40%, drawdown >=25%, or "
    "selected holding allocation >=40%; MODERATE at volatility >=20%, "
    "drawdown >=10%, or allocation >=20%; otherwise LOW when a risk value "
    "exists, else UNKNOWN."
)


def _valid(value: float | None) -> bool:
    return value is not None and isfinite(value)


def _factor(
    key: str,
    title: str,
    contribution: int,
    evidence: str,
) -> RiskMeterFactor:
    if key in {
        "volatility",
        "portfolio_volatility",
        "portfolio_drawdown",
        "concentration",
    }:
        direction = "RISK" if contribution < 0 else "NEUTRAL"
    elif contribution > 0:
        direction = "BULLISH"
    elif contribution < 0:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"
    return RiskMeterFactor(
        key=key,
        title=title,
        contribution=contribution,
        evidence=evidence,
        direction=direction,
    )


def build_risk_meter(
    *,
    symbol: str,
    exchange: Literal["NSE", "BSE"],
    period: Literal["1M", "3M", "6M", "1Y"],
    latest_close: float | None,
    indicators: dict[str, float | None],
    period_return_percent: float | None,
    annualized_volatility_percent: float | None,
    daily_return_observations: int,
    source: str | None,
    data_as_of: datetime | None,
    freshness_status: Literal["RECENT_HISTORY", "STALE_HISTORY", "UNKNOWN"] | None,
    candle_count: int,
    portfolio_context: RiskMeterPortfolioContext | None = None,
) -> RiskMeterResponse:
    values = RiskMeterValues(
        latest_close=latest_close,
        sma_20=indicators.get("sma_20"),
        ema_20=indicators.get("ema_20"),
        rsi_14=indicators.get("rsi_14"),
        macd=indicators.get("macd"),
        macd_signal=indicators.get("macd_signal"),
        period_return_percent=period_return_percent,
        annualized_volatility_percent=annualized_volatility_percent,
        portfolio_allocation_percent=(
            portfolio_context.allocation_percent if portfolio_context else None
        ),
        portfolio_annualized_volatility_percent=(
            portfolio_context.annualized_volatility_percent
            if portfolio_context
            else None
        ),
        portfolio_maximum_drawdown_percent=(
            portfolio_context.maximum_drawdown_percent if portfolio_context else None
        ),
    )

    factors: list[RiskMeterFactor] = []
    core_contributions: list[int] = []

    def add_core(
        key: str,
        title: str,
        contribution: int,
        evidence: str,
        valid: bool,
    ) -> None:
        if valid:
            core_contributions.append(contribution)
            factors.append(_factor(key, title, contribution, evidence))

    if _valid(latest_close) and _valid(values.sma_20):
        contribution = 12 if latest_close > values.sma_20 else -12
        add_core(
            "sma",
            "Close vs SMA 20",
            contribution,
            f"Close {latest_close:.2f} is "
            f"{'above' if contribution > 0 else 'at or below'} SMA 20 {values.sma_20:.2f}.",
            True,
        )
    if _valid(latest_close) and _valid(values.ema_20):
        contribution = 8 if latest_close > values.ema_20 else -8
        add_core(
            "ema",
            "Close vs EMA 20",
            contribution,
            f"Close {latest_close:.2f} is "
            f"{'above' if contribution > 0 else 'at or below'} EMA 20 {values.ema_20:.2f}.",
            True,
        )
    if _valid(values.rsi_14):
        rsi_value = values.rsi_14
        if rsi_value >= 70:
            contribution = -8
        elif rsi_value >= 60:
            contribution = 6
        elif rsi_value >= 55:
            contribution = 3
        elif rsi_value > 45:
            contribution = 0
        elif rsi_value > 40:
            contribution = -3
        elif rsi_value >= 30:
            contribution = -6
        else:
            contribution = -8
        add_core(
            "rsi",
            "RSI 14 momentum",
            contribution,
            (
                f"RSI 14 is {rsi_value:.2f}; "
                f"{'above 70 is treated as overheated' if rsi_value >= 70 else 'below 30 indicates weak momentum' if rsi_value < 30 else 'momentum contribution follows the documented RSI band'}."
            ),
            True,
        )
    if _valid(values.macd) and _valid(values.macd_signal):
        contribution = 12 if values.macd > values.macd_signal else -12
        add_core(
            "macd",
            "MACD vs signal",
            contribution,
            f"MACD {values.macd:.4f} is "
            f"{'above' if contribution > 0 else 'at or below'} signal {values.macd_signal:.4f}.",
            True,
        )
    if _valid(period_return_percent):
        contribution = (
            10 if period_return_percent >= 5 else
            5 if period_return_percent > 0 else
            -10 if period_return_percent <= -5 else
            -5 if period_return_percent < 0 else
            0
        )
        add_core(
            "return",
            f"{period} historical return",
            contribution,
            f"{period} close-to-close return is {period_return_percent:.2f}%.",
            True,
        )

    if _valid(annualized_volatility_percent):
        volatility = annualized_volatility_percent
        if volatility > 60:
            contribution = -10
        elif volatility > 40:
            contribution = -5
        elif volatility <= 20:
            contribution = 2
        else:
            contribution = 0
        factors.append(
            _factor(
                "volatility",
                "Instrument historical volatility",
                contribution,
                f"Annualized historical volatility is {volatility:.2f}%.",
            )
        )
    if portfolio_context:
        portfolio_volatility = portfolio_context.annualized_volatility_percent
        if _valid(portfolio_volatility):
            contribution = (
                -6 if portfolio_volatility > 60
                else -3 if portfolio_volatility > 40
                else 0
            )
            factors.append(
                _factor(
                    "portfolio_volatility",
                    "Portfolio historical volatility",
                    contribution,
                    f"{portfolio_context.portfolio_name} annualized volatility is {portfolio_volatility:.2f}%.",
                )
            )
        drawdown = portfolio_context.maximum_drawdown_percent
        if _valid(drawdown):
            contribution = -8 if drawdown > 30 else -4 if drawdown > 15 else 0
            factors.append(
                _factor(
                    "portfolio_drawdown",
                    "Portfolio maximum drawdown",
                    contribution,
                    f"{portfolio_context.portfolio_name} maximum drawdown is {drawdown:.2f}%.",
                )
            )
        allocation = portfolio_context.allocation_percent
        if _valid(allocation):
            contribution = (
                -12 if allocation > 50
                else -8 if allocation > 35
                else -4 if allocation > 20
                else 0
            )
            factors.append(
                _factor(
                    "concentration",
                    "Holding portfolio concentration",
                    contribution,
                    f"{symbol} represents {allocation:.2f}% of valued portfolio assets.",
                )
            )

    status: AssessmentStatus
    if freshness_status == "STALE_HISTORY":
        status = "STALE_HISTORY"
    elif freshness_status != "RECENT_HISTORY":
        status = "UNKNOWN_FRESHNESS"
    elif len(core_contributions) < 3:
        status = "INSUFFICIENT_DATA"
    else:
        status = "READY"

    if core_contributions:
        directional = [value for value in core_contributions if value != 0]
        agreement = (
            max(
                sum(value > 0 for value in directional),
                sum(value < 0 for value in directional),
            )
            / len(directional)
            if directional
            else 0.5
        )
        confidence_percent = round(
            len(core_contributions) / 5 * 70 + agreement * 30
        )
    else:
        confidence_percent = 0
    confidence_level: ConfidenceLevel = (
        "HIGH" if confidence_percent >= 80 else
        "MODERATE" if confidence_percent >= 60 else
        "LOW"
    )

    score = (
        max(0, min(100, round(50 + sum(factor.contribution for factor in factors))))
        if len(core_contributions) >= 3
        else None
    )
    recommendation: Recommendation = "NOT AVAILABLE"
    if status == "READY" and score is not None:
        recommendation = (
            "BUY" if score >= 65 else
            "SELL / REDUCE EXPOSURE" if score <= 35 else
            "HOLD"
        )

    known_risk_values = [
        value
        for value in (
            annualized_volatility_percent,
            portfolio_context.annualized_volatility_percent
            if portfolio_context
            else None,
            portfolio_context.maximum_drawdown_percent if portfolio_context else None,
            portfolio_context.allocation_percent if portfolio_context else None,
        )
        if _valid(value)
    ]
    high_risk = (
        (_valid(annualized_volatility_percent) and annualized_volatility_percent >= 40)
        or (
            portfolio_context is not None
            and _valid(portfolio_context.annualized_volatility_percent)
            and portfolio_context.annualized_volatility_percent >= 40
        )
        or (
            portfolio_context is not None
            and _valid(portfolio_context.maximum_drawdown_percent)
            and portfolio_context.maximum_drawdown_percent >= 25
        )
        or (
            portfolio_context is not None
            and _valid(portfolio_context.allocation_percent)
            and portfolio_context.allocation_percent >= 40
        )
    )
    moderate_risk = (
        (_valid(annualized_volatility_percent) and annualized_volatility_percent >= 20)
        or (
            portfolio_context is not None
            and _valid(portfolio_context.annualized_volatility_percent)
            and portfolio_context.annualized_volatility_percent >= 20
        )
        or (
            portfolio_context is not None
            and _valid(portfolio_context.maximum_drawdown_percent)
            and portfolio_context.maximum_drawdown_percent >= 10
        )
        or (
            portfolio_context is not None
            and _valid(portfolio_context.allocation_percent)
            and portfolio_context.allocation_percent >= 20
        )
    )
    risk_level: RiskLevel = (
        "HIGH" if high_risk else
        "MODERATE" if moderate_risk else
        "LOW" if known_risk_values else
        "UNKNOWN"
    )

    ordered_factors = sorted(
        factors, key=lambda factor: abs(factor.contribution), reverse=True
    )
    bullish_evidence = [
        factor.evidence for factor in factors if factor.direction == "BULLISH"
    ]
    bearish_evidence = [
        factor.evidence for factor in factors if factor.direction in {"BEARISH", "RISK"}
    ]
    what_could_change = [
        "A new completed daily candle can change the moving-average, RSI, MACD, and return signals.",
        "A change in historical volatility, drawdown, or holding concentration can change the risk adjustments.",
    ]
    if portfolio_context is None:
        what_could_change.append(
            "Selecting one of your portfolios can add portfolio volatility, drawdown, and holding-concentration evidence."
        )
    if status != "READY":
        what_could_change.insert(
            0,
            "A recommendation is withheld until validated, sufficiently complete, recent historical data is available.",
        )

    limitations = [
        "This deterministic meter describes historical indicators; it is not personalized financial advice or a forecast.",
        "No automatic order or trade is created from this assessment.",
        "Daily data may omit sessions and does not adjust for dividends or corporate actions.",
        "Missing indicator values contribute no points and reduce confidence; fewer than three core signals suppress the score.",
        "Gemini, when requested, can only produce a separate explanation and cannot alter this score or recommendation.",
    ]
    if status != "READY":
        limitations.append(
            f"Assessment status is {status}; the score is informational only and no recommendation is issued."
        )

    return RiskMeterResponse(
        symbol=symbol,
        exchange=exchange,
        period=period,
        status=status,
        score=score,
        recommendation=recommendation,
        confidence_percent=confidence_percent,
        confidence_level=confidence_level,
        risk_level=risk_level,
        source=source,
        data_as_of=data_as_of,
        freshness_status=freshness_status,
        candle_count=candle_count,
        daily_return_observations=daily_return_observations,
        values=values,
        factors=factors,
        top_factors=ordered_factors[:3],
        bullish_evidence=bullish_evidence,
        bearish_evidence=bearish_evidence,
        what_could_change=what_could_change,
        formula=FORMULA,
        limitations=limitations,
        portfolio_context=portfolio_context,
        ai_explanation_status="NOT_REQUESTED",
        ai_explanation=None,
        ai_explanation_message=None,
    )


def apply_ai_explanation(
    assessment: RiskMeterResponse,
    *,
    summary: str | None = None,
    error_message: str | None = None,
    configured: bool = True,
) -> RiskMeterResponse:
    if not configured:
        assessment.ai_explanation_status = "NOT_CONFIGURED"
        assessment.ai_explanation_message = (
            "Gemini is not configured; the deterministic assessment is unchanged."
        )
    elif error_message:
        assessment.ai_explanation_status = "ERROR"
        assessment.ai_explanation_message = error_message
    elif summary:
        assessment.ai_explanation_status = "AVAILABLE"
        assessment.ai_explanation = summary
    else:
        assessment.ai_explanation_status = "ERROR"
        assessment.ai_explanation_message = "Gemini returned no explanation."
    return assessment
