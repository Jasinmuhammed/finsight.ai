export type RiskMeterFactor = {
  key: string;
  title: string;
  contribution: number;
  evidence: string;
  direction: "BULLISH" | "BEARISH" | "NEUTRAL" | "RISK";
};

export type RiskMeterResponse = {
  symbol: string;
  exchange: "NSE" | "BSE";
  period: "1M" | "3M" | "6M" | "1Y";
  status: "READY" | "INSUFFICIENT_DATA" | "STALE_HISTORY" | "UNKNOWN_FRESHNESS";
  score: number | null;
  recommendation: "BUY" | "HOLD" | "SELL / REDUCE EXPOSURE" | "NOT AVAILABLE";
  confidence_percent: number;
  confidence_level: "LOW" | "MODERATE" | "HIGH";
  risk_level: "LOW" | "MODERATE" | "HIGH" | "UNKNOWN";
  source: string | null;
  data_as_of: string | null;
  freshness_status: "RECENT_HISTORY" | "STALE_HISTORY" | "UNKNOWN" | null;
  candle_count: number;
  daily_return_observations: number;
  values: {
    latest_close: number | null;
    sma_20: number | null;
    ema_20: number | null;
    rsi_14: number | null;
    macd: number | null;
    macd_signal: number | null;
    period_return_percent: number | null;
    annualized_volatility_percent: number | null;
    portfolio_allocation_percent: number | null;
    portfolio_annualized_volatility_percent: number | null;
    portfolio_maximum_drawdown_percent: number | null;
  };
  factors: RiskMeterFactor[];
  top_factors: RiskMeterFactor[];
  bullish_evidence: string[];
  bearish_evidence: string[];
  what_could_change: string[];
  formula: string;
  limitations: string[];
  portfolio_context: {
    portfolio_name: string;
    allocation_percent: number | null;
    annualized_volatility_percent: number | null;
    maximum_drawdown_percent: number | null;
    data_as_of: string | null;
  } | null;
  ai_explanation_status: "NOT_REQUESTED" | "NOT_CONFIGURED" | "AVAILABLE" | "ERROR";
  ai_explanation: string | null;
  ai_explanation_message: string | null;
};
