import type { RiskMeterResponse } from "@/types/risk-meter";

function formatMetric(value: number | null, digits = 2) {
  return value === null ? "Unavailable" : value.toFixed(digits);
}

function formatPercent(value: number | null) {
  return value === null ? "Unavailable" : `${value.toFixed(2)}%`;
}

function formatTimestamp(value: string | null) {
  return value
    ? new Date(value).toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Kolkata",
        timeZoneName: "short",
      })
    : "Not available";
}

export function RiskMeterReport({
  assessment,
  onExplain,
  explanationLoading = false,
}: {
  assessment: RiskMeterResponse;
  onExplain?: () => void;
  explanationLoading?: boolean;
}) {
  return (
    <div className="risk-meter-report">
      <div className={`risk-meter-result risk-meter-${assessment.recommendation === "BUY" ? "buy" : assessment.recommendation === "SELL / REDUCE EXPOSURE" ? "sell" : "hold"}`}>
        <div>
          <strong>{assessment.score === null ? "Score unavailable" : `${assessment.score} / 100`}</strong>
          <span>{assessment.recommendation}</span>
        </div>
        <div className="risk-meter-tags">
          <span>Confidence · {assessment.confidence_level} ({assessment.confidence_percent}%)</span>
          <span>Risk · {assessment.risk_level}</span>
          <span>Status · {assessment.status.replaceAll("_", " ")}</span>
        </div>
      </div>
      <p className="data-provenance">
        {assessment.source ?? "Historical source unavailable"} · {assessment.candle_count} daily candles · as of{" "}
        {formatTimestamp(assessment.data_as_of)} ·{" "}
        {assessment.freshness_status?.replaceAll("_", " ") ?? "freshness unknown"}.
      </p>
      {assessment.status !== "READY" && (
        <p className="provider-warning" role="status">
          No BUY/HOLD/SELL assessment is issued because the data is stale, incomplete, or its freshness is unknown.
        </p>
      )}

      <section aria-labelledby="risk-meter-why">
        <h3 id="risk-meter-why">Why This Decision?</h3>
        <ol className="risk-meter-factors">
          {assessment.top_factors.map((factor) => (
            <li key={factor.key}>
              <strong>{factor.title} · {factor.contribution > 0 ? "+" : ""}{factor.contribution} points</strong>
              <span>{factor.evidence}</span>
            </li>
          ))}
          {!assessment.top_factors.length && <li>No validated contributing factors are available.</li>}
        </ol>
      </section>

      <div className="risk-meter-evidence">
        <section>
          <h3>Bullish evidence</h3>
          {assessment.bullish_evidence.length ? (
            <ul>{assessment.bullish_evidence.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : <p>No bullish evidence from the available inputs.</p>}
        </section>
        <section>
          <h3>Bearish and risk evidence</h3>
          {assessment.bearish_evidence.length ? (
            <ul>{assessment.bearish_evidence.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : <p>No bearish or risk deductions from the available inputs.</p>}
        </section>
      </div>

      <section>
        <h3>Verified values</h3>
        <dl className="risk-meter-values">
          <div><dt>Latest close</dt><dd>{formatMetric(assessment.values.latest_close)}</dd></div>
          <div><dt>SMA 20</dt><dd>{formatMetric(assessment.values.sma_20)}</dd></div>
          <div><dt>EMA 20</dt><dd>{formatMetric(assessment.values.ema_20)}</dd></div>
          <div><dt>RSI 14</dt><dd>{formatMetric(assessment.values.rsi_14)}</dd></div>
          <div><dt>MACD / signal</dt><dd>{formatMetric(assessment.values.macd, 4)} / {formatMetric(assessment.values.macd_signal, 4)}</dd></div>
          <div><dt>{assessment.period} return</dt><dd>{formatPercent(assessment.values.period_return_percent)}</dd></div>
          <div><dt>Annualized volatility</dt><dd>{formatPercent(assessment.values.annualized_volatility_percent)}</dd></div>
          <div><dt>Portfolio holding allocation</dt><dd>{formatPercent(assessment.values.portfolio_allocation_percent)}</dd></div>
          <div><dt>Portfolio volatility / drawdown</dt><dd>{formatPercent(assessment.values.portfolio_annualized_volatility_percent)} / {formatPercent(assessment.values.portfolio_maximum_drawdown_percent)}</dd></div>
        </dl>
      </section>

      <section>
        <h3>What could change this assessment?</h3>
        <ul className="risk-meter-list">{assessment.what_could_change.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <details className="risk-meter-formula">
        <summary>Scoring formula and limitations</summary>
        <p>{assessment.formula}</p>
        <ul>{assessment.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>

      {onExplain && (
        <section className="risk-meter-ai">
          <div className="section-heading compact">
            <div>
              <h3>Optional Gemini explanation</h3>
              <p className="muted">Gemini receives only these calculated fields and cannot change the score or recommendation.</p>
            </div>
            <button className="secondary-button" disabled={explanationLoading} onClick={onExplain} type="button">
              {explanationLoading ? "Explaining…" : "Explain verified calculations"}
            </button>
          </div>
          {assessment.ai_explanation_status === "AVAILABLE" && assessment.ai_explanation && (
            <p className="ai-risk-explanation" aria-live="polite">{assessment.ai_explanation}</p>
          )}
          {assessment.ai_explanation_status === "NOT_CONFIGURED" && (
            <p className="muted" role="status">{assessment.ai_explanation_message}</p>
          )}
          {assessment.ai_explanation_status === "ERROR" && (
            <p className="error-state inline-error" role="status">{assessment.ai_explanation_message}</p>
          )}
        </section>
      )}
    </div>
  );
}
