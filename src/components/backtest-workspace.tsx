"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

type Trade = {
  entry_at: string;
  exit_at: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  fees: number;
  net_pnl: number;
  return_percent: number;
  exit_reason: string;
};

type BacktestResult = {
  initial_capital: number;
  final_capital: number;
  net_profit: number;
  total_return_percent: number;
  annualized_return_percent: number | null;
  maximum_drawdown_percent: number;
  win_rate_percent: number;
  trade_count: number;
  average_win: number | null;
  average_loss: number | null;
  profit_factor: number | null;
  sharpe_ratio: number | null;
  trades: Trade[];
  equity_curve: { timestamp: string; equity: number; drawdown_percent: number }[];
  assumptions: string[];
  data_status: "HISTORICAL";
};

type BacktestResponse = {
  id: string;
  symbol: string;
  exchange: string;
  source: string;
  result: BacktestResult;
};

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const width = 900;
const height = 220;

function formatMoney(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

export function BacktestWorkspace() {
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [entryRule, setEntryRule] = useState<"sma_crossover" | "range_breakout">("sma_crossover");
  const [fastPeriod, setFastPeriod] = useState("10");
  const [slowPeriod, setSlowPeriod] = useState("20");
  const [lookback, setLookback] = useState("20");
  const [initialCapital, setInitialCapital] = useState("100000");
  const [positionSize, setPositionSize] = useState("100");
  const [brokerage, setBrokerage] = useState("10");
  const [slippage, setSlippage] = useState("10");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const response = await fetch(`${apiBase}/backtests/run`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol.trim().toUpperCase(),
          exchange,
          start: start || null,
          end: end || null,
          strategy: {
            entry_rule: entryRule,
            fast_period: Number(fastPeriod),
            slow_period: Number(slowPeriod),
            breakout_lookback: Number(lookback),
            initial_capital: Number(initialCapital),
            position_size_percent: Number(positionSize),
            brokerage_bps: Number(brokerage),
            slippage_bps: Number(slippage),
            stop_loss_percent: stopLoss ? Number(stopLoss) : null,
            take_profit_percent: takeProfit ? Number(takeProfit) : null,
          },
        }),
      });
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail || `Backtest request failed (${response.status}).`);
      }
      setResult((await response.json()) as BacktestResponse);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to run this backtest.");
    } finally {
      setLoading(false);
    }
  }

  const equity = result?.result.equity_curve ?? [];
  const values = equity.map((point) => point.equity);
  const minimum = Math.min(...values, 0);
  const maximum = Math.max(...values, 1);
  const path = equity
    .map((point, index) => {
      const x = 8 + (index / Math.max(equity.length - 1, 1)) * (width - 16);
      const y = 8 + ((maximum - point.equity) / Math.max(maximum - minimum, 1)) * (height - 16);
      return `${index === 0 ? "M" : "L"}${x},${y}`;
    })
    .join(" ");

  return (
    <div className="page-stack">
      <section className="section-card">
        <div className="section-heading compact">
          <div><p className="eyebrow">SIMULATION CONFIGURATION</p><h2>Set strategy and assumptions</h2></div>
          <span className="demo-tag historical-tag">DAILY HISTORICAL DATA</span>
        </div>
        <p className="data-provenance">Runs only on configured daily historical candles; results are not live prices or predictions. A signal at a daily close is filled at the next available daily open. No simulated market prices are used.</p>
        <form className="backtest-form" onSubmit={run}>
          <label className="field"><span>Symbol</span><input maxLength={32} onChange={(event) => setSymbol(event.target.value)} placeholder="e.g. RELIANCE" required value={symbol} /></label>
          <label className="field"><span>Exchange</span><select onChange={(event) => setExchange(event.target.value)} value={exchange}><option value="NSE">NSE</option><option value="BSE">BSE</option></select></label>
          <label className="field"><span>Entry strategy</span><select onChange={(event) => setEntryRule(event.target.value as "sma_crossover" | "range_breakout")} value={entryRule}><option value="sma_crossover">SMA crossover</option><option value="range_breakout">Historical range breakout</option></select></label>
          {entryRule === "sma_crossover" ? (
            <>
              <label className="field"><span>Fast SMA</span><input min="2" max="252" onChange={(event) => setFastPeriod(event.target.value)} required type="number" value={fastPeriod} /></label>
              <label className="field"><span>Slow SMA</span><input min="3" max="504" onChange={(event) => setSlowPeriod(event.target.value)} required type="number" value={slowPeriod} /></label>
            </>
          ) : <label className="field"><span>Breakout lookback bars</span><input min="2" max="252" onChange={(event) => setLookback(event.target.value)} required type="number" value={lookback} /></label>}
          <label className="field"><span>Initial capital (₹)</span><input min="1" onChange={(event) => setInitialCapital(event.target.value)} required type="number" value={initialCapital} /></label>
          <label className="field"><span>Position size (%)</span><input min="0.01" max="100" onChange={(event) => setPositionSize(event.target.value)} required step="0.01" type="number" value={positionSize} /></label>
          <label className="field"><span>Brokerage (bps / side)</span><input min="0" max="5000" onChange={(event) => setBrokerage(event.target.value)} required step="0.1" type="number" value={brokerage} /></label>
          <label className="field"><span>Slippage (bps / side)</span><input min="0" max="5000" onChange={(event) => setSlippage(event.target.value)} required step="0.1" type="number" value={slippage} /></label>
          <label className="field"><span>Stop loss (%) · optional</span><input min="0.01" max="99.99" onChange={(event) => setStopLoss(event.target.value)} step="0.01" type="number" value={stopLoss} /></label>
          <label className="field"><span>Take profit (%) · optional</span><input min="0.01" max="1000" onChange={(event) => setTakeProfit(event.target.value)} step="0.01" type="number" value={takeProfit} /></label>
          <label className="field"><span>From</span><input onChange={(event) => setStart(event.target.value)} type="date" value={start} /></label>
          <label className="field"><span>To</span><input onChange={(event) => setEnd(event.target.value)} type="date" value={end} /></label>
          <button className="primary-button" disabled={loading} type="submit">{loading ? "Simulating…" : "Run backtest"}</button>
        </form>
      </section>

      {error && (
        <section className="section-card error-state portfolio-error" role="alert">
          <strong>Backtest could not be completed</strong><p>{error}</p>
          {error.includes("Authentication") && <Link className="text-link" href="/login">Sign in to run and save a backtest</Link>}
        </section>
      )}
      {result && (
        <>
          <section className="section-card">
            <div className="section-heading compact"><div><p className="eyebrow">{result.exchange} · {result.symbol} · HISTORICAL SIMULATION</p><h2>Backtest results</h2></div><span className="updated-label">{result.source}</span></div>
            <div className="metric-grid backtest-metrics">
              <article className="metric-card"><p className="metric-label">Final capital</p><p className="metric-value">{formatMoney(result.result.final_capital)}</p><p className="metric-note">Starting at {formatMoney(result.result.initial_capital)}</p></article>
              <article className="metric-card"><p className="metric-label">Net return</p><p className={`metric-value ${result.result.total_return_percent >= 0 ? "positive" : "negative"}`}>{result.result.total_return_percent.toFixed(2)}%</p><p className="metric-note">Net profit {formatMoney(result.result.net_profit)}</p></article>
              <article className="metric-card"><p className="metric-label">Maximum drawdown</p><p className="metric-value">{result.result.maximum_drawdown_percent.toFixed(2)}%</p><p className="metric-note">Peak-to-trough historical equity</p></article>
              <article className="metric-card"><p className="metric-label">Win rate</p><p className="metric-value">{result.result.win_rate_percent.toFixed(2)}%</p><p className="metric-note">{result.result.trade_count} closed trades</p></article>
              <article className="metric-card"><p className="metric-label">Annualized return</p><p className="metric-value">{result.result.annualized_return_percent === null ? "—" : `${result.result.annualized_return_percent.toFixed(2)}%`}</p><p className="metric-note">Shown only for periods of at least one year</p></article>
              <article className="metric-card"><p className="metric-label">Profit factor</p><p className="metric-value">{result.result.profit_factor === null ? "—" : result.result.profit_factor.toFixed(2)}</p><p className="metric-note">Gross wins / gross losses</p></article>
              <article className="metric-card"><p className="metric-label">Sharpe ratio</p><p className="metric-value">{result.result.sharpe_ratio === null ? "—" : result.result.sharpe_ratio.toFixed(2)}</p><p className="metric-note">Annualized from daily equity returns</p></article>
              <article className="metric-card"><p className="metric-label">Average win / loss</p><p className="metric-value">{formatMoney(result.result.average_win)} / {formatMoney(result.result.average_loss)}</p><p className="metric-note">Per closed trade</p></article>
            </div>
          </section>
          <section className="section-card">
            <div className="section-heading compact"><div><p className="eyebrow">EQUITY CURVE</p><h2>Historical account value</h2></div></div>
            <div className="equity-chart-wrap"><svg aria-label="Historical simulated equity curve" role="img" viewBox={`0 0 ${width} ${height}`}><line className="chart-gridline" x1="0" x2={width} y1={height / 2} y2={height / 2} /><path className="equity-line" d={path} /></svg></div>
            <p className="table-footnote">The curve includes open-position mark-to-market values and closes remaining positions at the final available close.</p>
          </section>
          <section className="section-card">
            <div className="section-heading compact"><div><p className="eyebrow">TRADE LOG</p><h2>Closed trades</h2></div></div>
            {result.result.trades.length ? <div className="table-wrap"><table><thead><tr><th>Entry</th><th>Exit</th><th>Quantity</th><th>Entry price</th><th>Exit price</th><th>Fees</th><th>Net P&amp;L</th><th>Exit reason</th></tr></thead><tbody>{result.result.trades.map((trade, index) => <tr key={`${trade.entry_at}-${index}`}><td>{new Date(trade.entry_at).toLocaleDateString()}</td><td>{new Date(trade.exit_at).toLocaleDateString()}</td><td>{trade.quantity}</td><td>{formatMoney(trade.entry_price)}</td><td>{formatMoney(trade.exit_price)}</td><td>{formatMoney(trade.fees)}</td><td className={trade.net_pnl >= 0 ? "positive" : "negative"}>{formatMoney(trade.net_pnl)}</td><td>{trade.exit_reason.replaceAll("_", " ")}</td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>No completed trades</strong><p>There were no fully formed signals in the selected history.</p></div>}
          </section>
          <section className="section-card">
            <div className="section-heading compact"><div><p className="eyebrow">MODEL LIMITATIONS</p><h2>Execution assumptions</h2></div></div>
            <ul className="risk-assumptions">{result.result.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
          </section>
        </>
      )}
    </div>
  );
}
