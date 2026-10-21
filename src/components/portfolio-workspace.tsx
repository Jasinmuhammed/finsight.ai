"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { RiskMeterReport } from "@/components/risk-meter-report";
import type { RiskMeterResponse } from "@/types/risk-meter";

type Portfolio = {
  id: string;
  name: string;
  currency: string;
  initial_cash: number;
};

type Transaction = {
  id: string;
  symbol: string;
  exchange: "NSE" | "BSE";
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  fees: number;
  transacted_at: string;
};

type Holding = {
  symbol: string;
  exchange: string;
  quantity: number;
  average_cost: number;
  invested_amount: number;
  historical_last_close: number | null;
  market_value: number | null;
  realized_pnl: number;
  unrealized_pnl: number | null;
  allocation_percent: number | null;
  price_status: string;
  price_message: string | null;
  price_as_of: string | null;
  freshness_status: string;
};

type Overview = {
  portfolio_id: string;
  initial_cash: number;
  cash_balance: number;
  total_invested_capital: number;
  cash_allocation_percent: number | null;
  total_value: number | null;
  realized_pnl: number;
  unrealized_pnl: number | null;
  valuation_status: string;
  price_source: string;
  freshness_status: string;
  data_as_of: string | null;
  holdings: Holding[];
  risk: {
    observations: number;
    annualized_volatility_percent: number | null;
    maximum_drawdown_percent: number | null;
    correlation: Record<string, Record<string, number | null>>;
    assumptions: string[];
  };
};

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

function localDateTimeValue() {
  const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function formatCurrency(value: number | null) {
  if (value === null) return "Unavailable";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatMarketTimestamp(value: string | null) {
  if (!value) return "Not available";
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "Timestamp unavailable";
  return timestamp.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
    timeZoneName: "short",
  });
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json()) as { detail?: string };
    throw new Error(body.detail || `Request failed (${response.status}).`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function PortfolioWorkspace() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [portfolioName, setPortfolioName] = useState("");
  const [initialCash, setInitialCash] = useState("100000");
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState<"NSE" | "BSE">("NSE");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [transactedAt, setTransactedAt] = useState(localDateTimeValue);
  const [editingId, setEditingId] = useState("");
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [savingTransaction, setSavingTransaction] = useState(false);
  const transactionSubmission = useRef(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [riskAssessment, setRiskAssessment] = useState<RiskMeterResponse | null>(null);
  const [riskMeterError, setRiskMeterError] = useState("");
  const [riskExplainLoading, setRiskExplainLoading] = useState(false);

  async function refreshPortfolio(portfolioId: string) {
    if (!portfolioId) return;
    setLoading(true);
    setError("");
    setRiskAssessment(null);
    setRiskMeterError("");
    try {
      const [overviewResponse, transactionsResponse] = await Promise.all([
        fetch(`${apiBase}/portfolios/${portfolioId}/overview`, { credentials: "include" }),
        fetch(`${apiBase}/portfolios/${portfolioId}/transactions?limit=100`, { credentials: "include" }),
      ]);
      const [nextOverview, nextTransactions] = await Promise.all([
        parseResponse<Overview>(overviewResponse),
        parseResponse<Transaction[]>(transactionsResponse),
      ]);
      setOverview(nextOverview);
      setTransactions(nextTransactions);
      setRiskAssessment(null);
      const focusHolding = [...nextOverview.holdings]
        .filter((holding) => holding.allocation_percent !== null)
        .sort(
          (left, right) =>
            (right.allocation_percent ?? 0) - (left.allocation_percent ?? 0),
        )[0];
      if (focusHolding) {
        try {
          const riskResponse = await fetch(`${apiBase}/risk-meter`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              symbol: focusHolding.symbol,
              exchange: focusHolding.exchange,
              period: "3M",
              portfolio_id: portfolioId,
            }),
          });
          const riskResult = await parseResponse<RiskMeterResponse>(riskResponse);
          setRiskAssessment(riskResult);
          setRiskMeterError("");
        } catch (riskError) {
          setRiskAssessment(null);
          setRiskMeterError(
            riskError instanceof Error
              ? riskError.message
              : "Holding risk assessment is unavailable.",
          );
        }
      } else {
        setRiskMeterError("");
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load portfolio.");
    } finally {
      setLoading(false);
    }
  }

  async function explainHoldingRisk() {
    if (!riskAssessment || !selectedId) return;
    setRiskExplainLoading(true);
    setRiskMeterError("");
    try {
      const response = await fetch(`${apiBase}/risk-meter`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: riskAssessment.symbol,
          exchange: riskAssessment.exchange,
          period: riskAssessment.period,
          portfolio_id: selectedId,
          include_ai_explanation: true,
        }),
      });
      const explained = await parseResponse<RiskMeterResponse>(response);
      setRiskAssessment(explained);
    } catch (requestError) {
      setRiskMeterError(
        requestError instanceof Error
          ? requestError.message
          : "Gemini explanation is unavailable; the deterministic score is unchanged.",
      );
    } finally {
      setRiskExplainLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBase}/portfolios`, { credentials: "include", signal: controller.signal })
      .then(parseResponse<Portfolio[]>)
      .then((items) => {
        setPortfolios(items);
        if (items[0]) {
          setSelectedId(items[0].id);
          void refreshPortfolio(items[0].id);
        }
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name !== "AbortError") {
          setError(requestError.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setInitialLoading(false);
      });
    return () => controller.abort();
  }, []);

  async function createPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${apiBase}/portfolios`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: portfolioName, initial_cash: Number(initialCash) }),
      });
      const created = await parseResponse<Portfolio>(response);
      setPortfolios((items) => [created, ...items]);
      setPortfolioName("");
      setSelectedId(created.id);
      setOverview(null);
      setTransactions([]);
      setNotice("Portfolio created.");
      void refreshPortfolio(created.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not create portfolio.");
    }
  }

  async function saveTransaction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || transactionSubmission.current) return;
    transactionSubmission.current = true;
    setSavingTransaction(true);
    setError("");
    setNotice("");
    const path = `${apiBase}/portfolios/${selectedId}/transactions`;
    const transaction = {
      symbol,
      exchange,
      side,
      quantity: Number(quantity),
      price: Number(price),
      fees: Number(fees),
      transacted_at: new Date(transactedAt).toISOString(),
    };
    try {
      const response = await fetch(
        editingId ? `${path}/${editingId}` : path,
        {
          method: editingId ? "PUT" : "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(transaction),
        },
      );
      await parseResponse<Transaction>(response);
      setNotice(editingId ? "Transaction updated." : "Transaction recorded.");
      resetTransactionForm();
      await refreshPortfolio(selectedId);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not record transaction.");
    } finally {
      transactionSubmission.current = false;
      setSavingTransaction(false);
    }
  }

  function resetTransactionForm() {
    setEditingId("");
    setSymbol("");
    setQuantity("");
    setPrice("");
    setFees("0");
    setSide("BUY");
    setTransactedAt(localDateTimeValue());
  }

  function editTransaction(item: Transaction) {
    const localTime = new Date(
      new Date(item.transacted_at).getTime() - new Date().getTimezoneOffset() * 60_000,
    );
    setEditingId(item.id);
    setSymbol(item.symbol);
    setExchange(item.exchange);
    setSide(item.side);
    setQuantity(String(item.quantity));
    setPrice(String(item.price));
    setFees(String(item.fees));
    setTransactedAt(localTime.toISOString().slice(0, 16));
  }

  async function deleteTransaction(item: Transaction) {
    if (!selectedId) return;
    setError("");
    setNotice("");
    try {
      const response = await fetch(
        `${apiBase}/portfolios/${selectedId}/transactions/${item.id}`,
        { method: "DELETE", credentials: "include" },
      );
      await parseResponse<void>(response);
      setNotice("Transaction removed.");
      if (editingId === item.id) resetTransactionForm();
      await refreshPortfolio(selectedId);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not remove transaction.");
    }
  }

  if (error.includes("401") || error === "Authentication required") {
    return (
      <section className="section-card empty-state">
        <strong>Sign in to view your private portfolio</strong>
        <p>Portfolio data is only available to its owner.</p>
        <Link className="text-link" href="/login">Sign in</Link>
      </section>
    );
  }

  if (initialLoading) {
    return <section className="section-card empty-state" role="status">Loading your portfolios…</section>;
  }

  const selectedHolding = overview?.holdings.find(
    (holding) => holding.symbol === symbol.trim().toUpperCase() && holding.exchange === exchange,
  );

  return (
    <div className="page-stack">
      {error && <div className="error-state portfolio-error" role="alert">{error}</div>}
      {notice && <div className="portfolio-notice" role="status">{notice}</div>}
      <section className="section-card portfolio-create-card">
        <div className="section-heading compact">
          <div><p className="eyebrow">WORKSPACE</p><h2>Portfolios</h2></div>
          {portfolios.length > 0 && (
            <label className="field portfolio-select">
              <span>Selected portfolio</span>
              <select onChange={(event) => {
                setSelectedId(event.target.value);
                void refreshPortfolio(event.target.value);
              }} value={selectedId}>
                {portfolios.map((portfolio) => <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>)}
              </select>
            </label>
          )}
        </div>
        <form className="portfolio-create-form" onSubmit={createPortfolio}>
          <label className="field"><span>New portfolio name</span><input maxLength={80} onChange={(event) => setPortfolioName(event.target.value)} required value={portfolioName} /></label>
          <label className="field"><span>Starting cash (₹)</span><input min="0" onChange={(event) => setInitialCash(event.target.value)} required step="0.01" type="number" value={initialCash} /></label>
          <button className="primary-button" type="submit">Create portfolio</button>
        </form>
      </section>

      {!portfolios.length ? (
        <section className="section-card empty-state"><strong>Create a portfolio to get started</strong><p>Set opening cash before recording purchases.</p></section>
      ) : (
        <>
          {overview && (
            <>
              <div className="notice" role="note">
                <span className="notice-dot" />
                <div><strong>Historical valuation · {overview.valuation_status}</strong><p>
                  Prices use {overview.price_source}; they are historical daily closes, not live quotes.
                  Freshness: {overview.freshness_status.replaceAll("_", " ").toLowerCase()}.
                  {overview.data_as_of && ` Latest available close: ${formatMarketTimestamp(overview.data_as_of)}.`}
                </p></div>
              </div>
              <div className="metric-grid portfolio-metrics">
                <article className="metric-card"><p className="metric-label">Cash balance</p><p className="metric-value">{formatCurrency(overview.cash_balance)}</p><p className="metric-note">{overview.cash_allocation_percent === null ? "Allocation unavailable" : `${overview.cash_allocation_percent.toFixed(2)}% of valued assets`} · after fees</p></article>
                <article className="metric-card"><p className="metric-label">Portfolio value</p><p className="metric-value">{formatCurrency(overview.total_value)}</p><p className="metric-note">Incomplete if a holding lacks history</p></article>
                <article className="metric-card"><p className="metric-label">Invested in open holdings</p><p className="metric-value">{formatCurrency(overview.total_invested_capital)}</p><p className="metric-note">Remaining average-cost basis, including allocated buy charges</p></article>
                <article className="metric-card"><p className="metric-label">Realized P&amp;L</p><p className={`metric-value ${overview.realized_pnl >= 0 ? "positive" : "negative"}`}>{formatCurrency(overview.realized_pnl)}</p><p className="metric-note">Average-cost accounting, net of sell fees</p></article>
                <article className="metric-card"><p className="metric-label">Unrealized P&amp;L</p><p className="metric-value">{formatCurrency(overview.unrealized_pnl)}</p><p className="metric-note">Uses last available historical closes</p></article>
              </div>

              <section className="section-card">
                <div className="section-heading compact"><div><p className="eyebrow">POSITIONS</p><h2>Holdings &amp; allocation</h2></div></div>
                {overview.holdings.length ? (
                  <div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Quantity</th><th>Average buy price</th><th>Invested amount</th><th>Historical price</th><th>Market value</th><th>Unrealized P&amp;L</th><th>Allocation</th></tr></thead>
                    <tbody>{overview.holdings.map((holding) => <tr key={`${holding.exchange}-${holding.symbol}`}>
                      <td><strong>{holding.symbol}</strong><small className="table-subtitle">{holding.exchange}</small></td>
                      <td>{holding.quantity}</td><td>{formatCurrency(holding.average_cost)}<small className="table-subtitle">Weighted average incl. buy charges</small></td>
                      <td>{formatCurrency(holding.invested_amount)}</td>
                      <td>{formatCurrency(holding.historical_last_close)}<small className="table-subtitle">{holding.price_as_of ? `${formatMarketTimestamp(holding.price_as_of)} · ${holding.freshness_status.replaceAll("_", " ").toLowerCase()}` : holding.price_message ?? holding.price_status}</small></td>
                      <td>{formatCurrency(holding.market_value)}</td><td className={holding.unrealized_pnl === null ? "" : holding.unrealized_pnl >= 0 ? "positive" : "negative"}>{formatCurrency(holding.unrealized_pnl)}</td>
                      <td>{holding.allocation_percent === null ? "—" : `${holding.allocation_percent.toFixed(2)}%`}</td>
                    </tr>)}</tbody></table></div>
                ) : <div className="empty-state"><strong>No holdings yet</strong><p>Record a buy transaction below.</p></div>}
              </section>

              <section className="section-card">
                <div className="section-heading compact"><div><p className="eyebrow">HISTORICAL RISK</p><h2>Portfolio risk</h2></div></div>
                <div className="risk-summary">
                  <div><small>Aligned daily observations</small><strong>{overview.risk.observations}</strong></div>
                  <div><small>Annualized volatility</small><strong>{overview.risk.annualized_volatility_percent === null ? "Insufficient data" : `${overview.risk.annualized_volatility_percent.toFixed(2)}%`}</strong></div>
                  <div><small>Maximum drawdown</small><strong>{overview.risk.maximum_drawdown_percent === null ? "Insufficient data" : `${overview.risk.maximum_drawdown_percent.toFixed(2)}%`}</strong></div>
                </div>
                {Object.keys(overview.risk.correlation).length > 1 && (
                  <div className="table-wrap risk-correlation">
                    <table>
                      <thead>
                        <tr>
                          <th>Instrument</th>
                          {Object.keys(overview.risk.correlation).map((key) => (
                            <th key={key}>{key}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(overview.risk.correlation).map(([left, values]) => (
                          <tr key={left}>
                            <td><strong>{left}</strong></td>
                            {Object.entries(values).map(([right, value]) => (
                              <td key={right}>{value === null ? "—" : value.toFixed(2)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <ul className="risk-assumptions">{overview.risk.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
              </section>
              <section className="section-card risk-meter-portfolio">
                <div className="section-heading compact">
                  <div>
                    <p className="eyebrow">CONCENTRATION-AWARE CONTEXT</p>
                    <h2>Largest holding risk meter</h2>
                    <p className="muted">The most concentrated valued holding is assessed with this portfolio&apos;s historical risk.</p>
                  </div>
                </div>
                {riskMeterError && <div className="error-state inline-error" role="alert">{riskMeterError}</div>}
                {riskAssessment && (
                  <RiskMeterReport
                    assessment={riskAssessment}
                    explanationLoading={riskExplainLoading}
                    onExplain={() => void explainHoldingRisk()}
                  />
                )}
                {!riskMeterError && !riskAssessment && overview.holdings.length === 0 && (
                  <p className="muted">Add a holding with an available historical valuation to calculate this meter.</p>
                )}
                {!riskMeterError && !riskAssessment && overview.holdings.length > 0 && (
                  <p className="muted" role="status">Calculating the largest valued holding&apos;s risk assessment…</p>
                )}
              </section>
            </>
          )}

          <section className="section-card">
            <div className="section-heading compact"><div><p className="eyebrow">{editingId ? "EDIT ENTRY" : "TRANSACTION LEDGER"}</p><h2>{editingId ? "Update transaction" : "Record a transaction"}</h2></div></div>
            <form className="transaction-form" onSubmit={saveTransaction}>
              <label className="field"><span>Symbol</span><input maxLength={32} onChange={(event) => setSymbol(event.target.value)} required value={symbol} /></label>
              <label className="field"><span>Exchange</span><select onChange={(event) => setExchange(event.target.value as "NSE" | "BSE")} value={exchange}><option value="NSE">NSE</option><option value="BSE">BSE</option></select></label>
              <label className="field"><span>Side</span><select onChange={(event) => setSide(event.target.value as "BUY" | "SELL")} value={side}><option value="BUY">Buy</option><option value="SELL">Sell</option></select></label>
              <label className="field"><span>Quantity</span><input max={side === "SELL" ? selectedHolding?.quantity : undefined} min="0.000001" onChange={(event) => setQuantity(event.target.value)} required step="any" type="number" value={quantity} />{side === "SELL" && <small>{selectedHolding ? `Available to sell: ${selectedHolding.quantity}` : "No matching shares are currently held."}</small>}</label>
              <label className="field"><span>Price (₹)</span><input min="0.01" onChange={(event) => setPrice(event.target.value)} required step="any" type="number" value={price} /></label>
              <label className="field"><span>Fees (₹)</span><input min="0" onChange={(event) => setFees(event.target.value)} required step="any" type="number" value={fees} /></label>
              <label className="field"><span>Transaction date and time</span><input onChange={(event) => setTransactedAt(event.target.value)} required type="datetime-local" value={transactedAt} /></label>
              <div className="transaction-actions"><button className="primary-button" disabled={loading || savingTransaction || (side === "SELL" && !selectedHolding)} type="submit">{savingTransaction ? "Saving…" : editingId ? "Save changes" : side === "BUY" ? "Record purchase" : "Record sale"}</button>
                {editingId && <button className="secondary-button" onClick={resetTransactionForm} type="button">Cancel edit</button>}</div>
            </form>
            <p className="table-footnote">Uses weighted-average cost basis. Buys reduce starting cash; sells are rejected if they exceed held quantity. Transactions do not fetch or invent current prices.</p>
          </section>

          <section className="section-card">
            <div className="section-heading compact"><div><p className="eyebrow">AUDIT TRAIL</p><h2>Transaction history</h2></div><span className="updated-label">{transactions.length} recent entries</span></div>
            {transactions.length ? (
              <div className="table-wrap"><table><thead><tr><th>Date</th><th>Instrument</th><th>Side</th><th>Quantity</th><th>Price</th><th>Fees</th><th>Actions</th></tr></thead>
                <tbody>{transactions.map((item) => <tr key={item.id}>
                  <td>{new Date(item.transacted_at).toLocaleString()}</td><td><strong>{item.symbol}</strong><small className="table-subtitle">{item.exchange}</small></td>
                  <td className={item.side === "BUY" ? "positive" : "negative"}>{item.side}</td><td>{item.quantity}</td><td>{formatCurrency(item.price)}</td><td>{formatCurrency(item.fees)}</td>
                  <td><button className="table-action" onClick={() => editTransaction(item)} type="button">Edit</button><button className="table-action danger" onClick={() => void deleteTransaction(item)} type="button">Delete</button></td>
                </tr>)}</tbody></table></div>
            ) : <div className="empty-state"><strong>No transactions yet</strong><p>Record your first buy or sell above.</p></div>}
          </section>
        </>
      )}
    </div>
  );
}
