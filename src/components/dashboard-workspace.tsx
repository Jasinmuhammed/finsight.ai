"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type ProviderStatus = {
  provider: string;
  status: string;
  configured: boolean;
  message: string;
};

type WatchlistItem = {
  id: string;
  symbol: string;
  exchange: "NSE" | "BSE";
};

type Watchlist = {
  id: string;
  name: string;
  instruments: WatchlistItem[];
};

type Portfolio = {
  id: string;
  name: string;
};

type PortfolioOverview = {
  cash_balance: number;
  total_value: number | null;
  realized_pnl: number;
  unrealized_pnl: number | null;
  valuation_status: string;
  price_source: string;
  freshness_status: string;
  data_as_of: string | null;
  risk: {
    observations: number;
    annualized_volatility_percent: number | null;
    maximum_drawdown_percent: number | null;
    assumptions: string[];
  };
  holdings: Holding[];
};

type Holding = {
  symbol: string;
  exchange: "NSE" | "BSE";
  quantity: number;
  average_cost: number;
  historical_last_close: number | null;
  market_value: number | null;
  realized_pnl: number;
  unrealized_pnl: number | null;
  allocation_percent: number | null;
  price_status: "HISTORICAL" | "UNAVAILABLE";
  price_as_of: string | null;
  freshness_status: string;
};

type Transaction = {
  id: string;
  symbol: string;
  exchange: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  transacted_at: string;
};

type AlertEvent = {
  id: string;
  symbol: string;
  exchange: string;
  message: string;
  created_at: string;
  data_as_of: string | null;
};

type NewsArticle = {
  source: string;
  source_id: string;
  headline: string;
  url: string;
  published_at: string;
  related_symbols: string[];
};

type InstrumentPerformance = {
  symbol: string;
  exchange: string;
  period_return_percent: number | null;
  freshness_status: string;
  source: string;
  data_as_of: string | null;
  error?: string;
};

type IndicatorResponse = {
  performance: {
    period_return_percent: number | null;
  };
  freshness_status: string;
  source: string;
  data_as_of: string | null;
};

type Instrument = {
  symbol: string;
  name: string;
  exchange: "NSE" | "BSE";
};

type HistoricalCandles = {
  candles: { timestamp: string; close: number }[];
  source: string;
  freshness_status: string;
  data_as_of: string | null;
};

type RiskAssessment = {
  symbol: string;
  exchange: string;
  score: number | null;
  recommendation: string;
  confidence_level: string;
  confidence_percent: number;
  risk_level: string;
  source: string | null;
  data_as_of: string | null;
  status: string;
  top_factors: { key: string; title: string; contribution: number; evidence: string }[];
};

type DashboardData = {
  provider: ProviderStatus | null;
  providerError: string;
  email: string | null;
  authError: string;
  watchlists: Watchlist[];
  watchlistError: string;
  watchlistPerformance: InstrumentPerformance[];
  portfolios: Portfolio[];
  portfolioOverview: PortfolioOverview | null;
  transactions: Transaction[];
  portfolioError: string;
  alerts: AlertEvent[];
  alertError: string;
  news: NewsArticle[];
  newsSource: string | null;
  newsError: string;
  chart: (HistoricalCandles & { symbol: string; exchange: string }) | null;
  chartError: string;
  riskAssessment: RiskAssessment | null;
  riskError: string;
};

const emptyData: DashboardData = {
  provider: null,
  providerError: "",
  email: null,
  authError: "",
  watchlists: [],
  watchlistError: "",
  watchlistPerformance: [],
  portfolios: [],
  portfolioOverview: null,
  transactions: [],
  portfolioError: "",
  alerts: [],
  alertError: "",
  news: [],
  newsSource: null,
  newsError: "",
  chart: null,
  chartError: "",
  riskAssessment: null,
  riskError: "",
};

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    credentials: "include",
    signal,
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status}).`;
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

async function postJson<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : `Request failed (${response.status}).`;
    throw new ApiError(detail, response.status);
  }
  return payload as T;
}

function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return "Unavailable";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(value: string | null) {
  if (!value) return "Not available";
  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  });
}

function indiaDate(daysAgo: number) {
  const date = new Date(Date.now() - daysAgo * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "This data could not be loaded.";
}

export function DashboardWorkspace() {
  const [data, setData] = useState(emptyData);
  const [loading, setLoading] = useState(true);
  const [instrumentQuery, setInstrumentQuery] = useState("");
  const [instrumentResults, setInstrumentResults] = useState<Instrument[]>([]);
  const [instrumentSearchError, setInstrumentSearchError] = useState("");
  const [instrumentSearchLoading, setInstrumentSearchLoading] = useState(false);

  async function searchInstruments(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = instrumentQuery.trim();
    if (!query) {
      setInstrumentResults([]);
      setInstrumentSearchError("Enter a symbol or company name to search.");
      return;
    }
    setInstrumentSearchLoading(true);
    setInstrumentSearchError("");
    try {
      const params = new URLSearchParams({ query, limit: "10" });
      setInstrumentResults(
        await getJson<Instrument[]>(`/market-data/instruments/search?${params}`),
      );
    } catch (error) {
      setInstrumentResults([]);
      setInstrumentSearchError(errorText(error));
    } finally {
      setInstrumentSearchLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    async function loadDashboard() {
      setLoading(true);
      const [providerResult, newsResult, userResult] = await Promise.allSettled([
        getJson<ProviderStatus>("/market-data/status", signal),
        getJson<{ source: string; articles: NewsArticle[] }>("/news?limit=4", signal),
        getJson<{ email: string }>("/auth/me", signal),
      ]);
      if (signal.aborted) return;

      const next: DashboardData = {
        ...emptyData,
        provider: providerResult.status === "fulfilled" ? providerResult.value : null,
        providerError:
          providerResult.status === "rejected" ? errorText(providerResult.reason) : "",
        news:
          newsResult.status === "fulfilled" ? newsResult.value.articles : [],
        newsSource:
          newsResult.status === "fulfilled" ? newsResult.value.source : null,
        newsError:
          newsResult.status === "rejected" ? errorText(newsResult.reason) : "",
      };

      if (userResult.status === "fulfilled") {
        next.email = userResult.value.email;
        const [watchlistResult, portfolioResult, alertResult] =
          await Promise.allSettled([
            getJson<Watchlist[]>("/watchlists", signal),
            getJson<Portfolio[]>("/portfolios", signal),
            getJson<AlertEvent[]>("/alerts/events?limit=5", signal),
          ]);
        if (signal.aborted) return;

        if (watchlistResult.status === "fulfilled") {
          next.watchlists = watchlistResult.value;
        } else {
          next.watchlistError = errorText(watchlistResult.reason);
        }
        if (portfolioResult.status === "fulfilled") {
          next.portfolios = portfolioResult.value;
        } else {
          next.portfolioError = errorText(portfolioResult.reason);
        }
        if (alertResult.status === "fulfilled") {
          next.alerts = alertResult.value;
        } else {
          next.alertError = errorText(alertResult.reason);
        }

        const selectedPortfolio = next.portfolios[0];
        if (selectedPortfolio) {
          const [overviewResult, transactionsResult] = await Promise.allSettled([
            getJson<PortfolioOverview>(
              `/portfolios/${selectedPortfolio.id}/overview`,
              signal,
            ),
            getJson<Transaction[]>(
              `/portfolios/${selectedPortfolio.id}/transactions?limit=5`,
              signal,
            ),
          ]);
          if (signal.aborted) return;
          if (overviewResult.status === "fulfilled") {
            next.portfolioOverview = overviewResult.value;
          } else {
            next.portfolioError = errorText(overviewResult.reason);
          }
          if (transactionsResult.status === "fulfilled") {
            next.transactions = transactionsResult.value;
          } else if (!next.portfolioError) {
            next.portfolioError = errorText(transactionsResult.reason);
          }
        }
      } else if (
        userResult.reason instanceof ApiError &&
        userResult.reason.status !== 401
      ) {
        next.authError = errorText(userResult.reason);
      }

      if (signal.aborted) return;
      setData(next);

      if (next.provider?.configured) {
        const uniqueInstruments = [
          ...new Map(
            next.watchlists
              .flatMap((watchlist) => watchlist.instruments)
              .map((item) => [`${item.exchange}:${item.symbol}`, item]),
          ).values(),
        ].slice(0, 6);
        const start = indiaDate(35);
        const end = indiaDate(1);
        const performance = await Promise.all(
          uniqueInstruments.map(async (item): Promise<InstrumentPerformance> => {
            try {
              const query = new URLSearchParams({
                start,
                end,
                limit: "100",
              });
              const result = await getJson<IndicatorResponse>(
                `/market-data/instruments/${item.exchange}/${encodeURIComponent(item.symbol)}/indicators?${query}`,
                signal,
              );
              return {
                symbol: item.symbol,
                exchange: item.exchange,
                period_return_percent:
                  result.performance.period_return_percent,
                freshness_status: result.freshness_status,
                source: result.source,
                data_as_of: result.data_as_of,
              };
            } catch (error) {
              return {
                symbol: item.symbol,
                exchange: item.exchange,
                period_return_percent: null,
                freshness_status: "UNAVAILABLE",
                source: "",
                data_as_of: null,
                error: errorText(error),
              };
            }
          }),
        );
        if (!signal.aborted) {
          setData((current) => ({ ...current, watchlistPerformance: performance }));
        }

        const chartInstrument = uniqueInstruments[0];
        const selectedPortfolio = next.portfolios[0];
        const valuedHolding = next.portfolioOverview?.holdings
          .filter((holding) => holding.market_value !== null)
          .sort(
            (left, right) =>
              (right.market_value ?? 0) - (left.market_value ?? 0),
          )[0];
        const [chartResult, riskResult] = await Promise.allSettled([
          chartInstrument
            ? getJson<HistoricalCandles>(
                `/market-data/instruments/${chartInstrument.exchange}/${encodeURIComponent(chartInstrument.symbol)}/candles?start=${start}&end=${end}&limit=100`,
                signal,
              ).then((chart) => ({
                ...chart,
                symbol: chartInstrument.symbol,
                exchange: chartInstrument.exchange,
              }))
            : Promise.resolve(null),
          selectedPortfolio && valuedHolding
            ? postJson<RiskAssessment>(
                "/risk-meter",
                {
                  symbol: valuedHolding.symbol,
                  exchange: valuedHolding.exchange,
                  period: "3M",
                  portfolio_id: selectedPortfolio.id,
                },
                signal,
              )
            : Promise.resolve(null),
        ]);
        if (!signal.aborted) {
          setData((current) => ({
            ...current,
            chart: chartResult.status === "fulfilled" ? chartResult.value : null,
            chartError: chartResult.status === "rejected"
              ? errorText(chartResult.reason)
              : "",
            riskAssessment:
              riskResult.status === "fulfilled" ? riskResult.value : null,
            riskError:
              riskResult.status === "rejected" ? errorText(riskResult.reason) : "",
          }));
        }
      }
      setLoading(false);
    }

    void loadDashboard().catch((error: unknown) => {
      if (!signal.aborted) {
        setData((current) => ({ ...current, authError: errorText(error) }));
        setLoading(false);
      }
    });

    return () => controller.abort();
  }, []);

  const recentActivity = [
    ...data.transactions.map((transaction) => ({
      id: transaction.id,
      date: transaction.transacted_at,
      description: `${transaction.side} ${transaction.quantity} ${transaction.exchange}:${transaction.symbol} at ${formatCurrency(transaction.price)}`,
      kind: "Portfolio transaction",
    })),
    ...data.alerts.map((alert) => ({
      id: alert.id,
      date: alert.created_at,
      description: alert.message,
      kind: "Historical alert event",
    })),
  ]
    .sort((left, right) => Date.parse(right.date) - Date.parse(left.date))
    .slice(0, 5);

  return (
    <div className="page-stack dashboard-workspace">
      <section className="welcome-row">
        <div>
          <p className="eyebrow">MARKET WORKSPACE</p>
          <h1>Dashboard</h1>
          <p className="muted">A source-aware summary of your saved workspace.</p>
        </div>
        <span className={`api-badge ${data.provider?.configured ? "connected" : "offline"}`} role="status">
          <span />
          {loading
            ? "Loading workspace"
            : data.provider?.configured
              ? `Historical data · ${data.provider.provider}`
              : "Historical data unavailable"}
        </span>
      </section>

      <section className="section-card dashboard-search">
        <form className="dashboard-search-form" onSubmit={(event) => void searchInstruments(event)}>
          <label className="field">
            <span>Search supported instruments</span>
            <input
              autoComplete="off"
              onChange={(event) => setInstrumentQuery(event.target.value)}
              placeholder="Search symbol (e.g. TCS)"
              value={instrumentQuery}
            />
          </label>
          <button className="primary-button" disabled={instrumentSearchLoading} type="submit">
            {instrumentSearchLoading ? "Searching…" : "Search"}
          </button>
          <Link className="secondary-button dashboard-search-link" href="/screener">Open screener</Link>
        </form>
        {instrumentSearchError && <p className="error-state inline-error" role="alert">{instrumentSearchError}</p>}
        {instrumentResults.length > 0 && (
          <ul className="dashboard-search-results" aria-label="Instrument search results">
            {instrumentResults.map((instrument) => (
              <li key={`${instrument.exchange}:${instrument.symbol}`}>
                <Link href={`/analysis?symbol=${encodeURIComponent(instrument.symbol)}&exchange=${instrument.exchange}`}>
                  <strong>{instrument.symbol}</strong>
                  <span>{instrument.name} · {instrument.exchange}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {!instrumentSearchLoading && instrumentQuery && !instrumentSearchError && instrumentResults.length === 0 && (
          <p className="muted" role="status">No supported instruments matched this search.</p>
        )}
      </section>

      <section className="dashboard-grid">
        <article className="section-card dashboard-market">
          <div className="section-heading compact">
            <div><p className="eyebrow">MARKET OVERVIEW</p><h2>Market indices</h2></div>
            <span className="demo-tag">{data.provider?.status ?? (loading ? "CHECKING" : "UNAVAILABLE")}</span>
          </div>
          <div className="index-unavailable">
            <strong>NIFTY 50 · SENSEX</strong>
            <span>No index data source is integrated. Values and movements are not available.</span>
          </div>
          <p className="data-provenance">
            {data.provider?.message ?? (data.providerError || "Checking configured market-data source.")} Historical instrument candles are not live or delayed quotes.
          </p>
          <Link className="text-link" href="/analysis">Analyze an instrument →</Link>
        </article>

        <article className="section-card dashboard-portfolio">
          <div className="section-heading compact">
            <div><p className="eyebrow">YOUR PORTFOLIO</p><h2>{data.portfolios[0]?.name ?? "Portfolio summary"}</h2></div>
            <Link className="text-link" href="/portfolio">Open →</Link>
          </div>
          {loading ? <p role="status">Loading private portfolio…</p> : data.authError ? (
            <div className="error-state inline-error" role="alert">{data.authError}</div>
          ) : !data.email ? (
            <p className="muted">Sign in to view your private portfolio. <Link className="text-link" href="/login">Sign in →</Link></p>
          ) : data.portfolioError ? (
            <div className="error-state inline-error" role="alert">{data.portfolioError}</div>
          ) : !data.portfolios.length ? (
            <div className="empty-state"><strong>No portfolio yet</strong><p>Create one to track transactions and historical risk.</p></div>
          ) : (
            <>
              <div className="dashboard-metrics">
                <div><small>Total value · historical</small><strong>{formatCurrency(data.portfolioOverview?.total_value)}</strong></div>
                <div><small>Available cash</small><strong>{formatCurrency(data.portfolioOverview?.cash_balance)}</strong></div>
                <div><small>Unrealized P&amp;L · holdings vs cost</small><strong className={data.portfolioOverview?.unrealized_pnl === null || data.portfolioOverview?.unrealized_pnl === undefined ? "" : data.portfolioOverview.unrealized_pnl >= 0 ? "positive" : "negative"}>{formatCurrency(data.portfolioOverview?.unrealized_pnl)}</strong></div>
                <div><small>Realized P&amp;L · completed sells</small><strong className={data.portfolioOverview?.realized_pnl === undefined ? "" : data.portfolioOverview.realized_pnl >= 0 ? "positive" : "negative"}>{formatCurrency(data.portfolioOverview?.realized_pnl)}</strong></div>
              </div>
              <p className="data-provenance">
                {data.portfolioOverview?.price_source ?? "Historical prices unavailable"} · as of {formatDate(data.portfolioOverview?.data_as_of ?? null)} · {data.portfolioOverview?.freshness_status ?? "UNKNOWN"}.
              </p>
              {data.portfolioOverview && (
                <p className="muted">
                  Risk: {data.portfolioOverview.risk.annualized_volatility_percent === null
                    ? "insufficient history for volatility"
                    : `${data.portfolioOverview.risk.annualized_volatility_percent.toFixed(2)}% annualized volatility`}
                  {" · "}
                  {data.portfolioOverview.risk.maximum_drawdown_percent === null
                    ? "drawdown unavailable"
                    : `${data.portfolioOverview.risk.maximum_drawdown_percent.toFixed(2)}% maximum drawdown`}
                  {" · "}{data.portfolioOverview.risk.observations} aligned daily returns.
                </p>
              )}
              {data.portfolioOverview?.holdings.length ? (
                <div className="table-wrap dashboard-holdings-wrap">
                  <table className="dashboard-holdings">
                    <thead><tr><th>Holding</th><th>Qty</th><th>Avg cost</th><th>Last close</th><th className="numeric">Value</th><th className="numeric">Unrealized P&amp;L</th></tr></thead>
                    <tbody>
                      {data.portfolioOverview.holdings.map((holding) => (
                        <tr key={`${holding.exchange}:${holding.symbol}`}>
                          <td><Link href={`/analysis?symbol=${encodeURIComponent(holding.symbol)}&exchange=${holding.exchange}`}><strong>{holding.symbol}</strong><span className="table-subtitle">{holding.exchange} · {holding.price_status === "HISTORICAL" ? holding.freshness_status : "Price unavailable"}</span></Link></td>
                          <td>{holding.quantity}</td>
                          <td>{formatCurrency(holding.average_cost)}</td>
                          <td>{formatCurrency(holding.historical_last_close)}</td>
                          <td className="numeric">{formatCurrency(holding.market_value)}</td>
                          <td className={`numeric ${holding.unrealized_pnl === null ? "" : holding.unrealized_pnl >= 0 ? "positive" : "negative"}`}>{formatCurrency(holding.unrealized_pnl)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="table-footnote">Average cost is based on your recorded buys/sells. Last close and market value use historical provider data; unavailable prices are not estimated.</p>
                </div>
              ) : null}
            </>
          )}
        </article>

        <article className="section-card dashboard-chart-card">
          <div className="section-heading compact">
            <div><p className="eyebrow">WATCHLIST CHART</p><h2>{data.chart ? `${data.chart.exchange}:${data.chart.symbol}` : "Historical price trend"}</h2></div>
            <Link className="text-link" href="/charts">Full chart →</Link>
          </div>
          {loading ? <p role="status">Loading historical closes…</p> : data.chartError ? (
            <div className="error-state inline-error" role="alert">{data.chartError}</div>
          ) : data.chart?.candles.length ? (
            <>
              <svg className="dashboard-sparkline" viewBox="0 0 640 180" role="img" aria-label={`${data.chart.symbol} daily historical closing prices`}>
                <title>{data.chart.symbol} daily historical closing prices</title>
                {(() => {
                  const values = data.chart.candles.map((candle) => candle.close);
                  const min = Math.min(...values);
                  const max = Math.max(...values);
                  const range = max - min || 1;
                  const path = values.map((value, index) => {
                    const x = values.length > 1 ? index / (values.length - 1) * 620 + 10 : 320;
                    const y = 155 - (value - min) / range * 130;
                    return `${index ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                  }).join(" ");
                  return <path d={path} />;
                })()}
              </svg>
              <div className="dashboard-chart-caption">
                <span>{formatCurrency(data.chart.candles[0].close)} → {formatCurrency(data.chart.candles[data.chart.candles.length - 1].close)}</span>
                <span>{data.chart.source} · {data.chart.freshness_status} · as of {formatDate(data.chart.data_as_of)}</span>
              </div>
            </>
          ) : (
            <div className="empty-state"><strong>No watchlist chart available</strong><p>Save an instrument to a watchlist and ensure its historical candles are supported by the selected provider.</p></div>
          )}
        </article>

        <article className="section-card dashboard-movers">
          <div className="section-heading compact">
            <div><p className="eyebrow">MARKET MOVERS</p><h2>Watchlist historical returns</h2></div>
            <Link className="text-link" href="/watchlists">Watchlists →</Link>
          </div>
          {loading ? <p role="status">Calculating historical returns…</p> : data.watchlistPerformance.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Instrument</th><th className="numeric">Recent historical return</th><th>Data source · freshness</th></tr></thead>
                <tbody>
                  {[...data.watchlistPerformance]
                    .sort((left, right) => (right.period_return_percent ?? -Infinity) - (left.period_return_percent ?? -Infinity))
                    .map((item) => (
                      <tr key={`${item.exchange}:${item.symbol}`}>
                        <td><Link href={`/analysis?symbol=${encodeURIComponent(item.symbol)}&exchange=${item.exchange}`}><strong>{item.exchange}:{item.symbol}</strong></Link></td>
                        <td className={`numeric ${item.period_return_percent === null ? "" : item.period_return_percent >= 0 ? "positive" : "negative"}`}>{item.period_return_percent === null ? "Unavailable" : `${item.period_return_percent >= 0 ? "+" : ""}${item.period_return_percent.toFixed(2)}%`}</td>
                        <td>{item.source || item.error || "Unavailable"}{item.freshness_status !== "UNAVAILABLE" ? ` · ${item.freshness_status}` : ""}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
              <p className="table-footnote">Movers are limited to saved watchlist instruments and use available historical closes, not intraday/live price changes.</p>
            </div>
          ) : <div className="empty-state"><strong>No historical movers to show</strong><p>Save supported instruments in a watchlist to compare their historical returns.</p></div>}
        </article>

        <article className="section-card dashboard-risk">
          <div className="section-heading compact">
            <div><p className="eyebrow">RISK &amp; EXPLAINABLE METER</p><h2>Largest valued holding</h2></div>
            <Link className="text-link" href="/portfolio">Portfolio analysis →</Link>
          </div>
          {loading ? <p role="status">Loading portfolio risk…</p> : !data.email ? (
            <p className="muted">Sign in to calculate your private portfolio risk assessment.</p>
          ) : data.riskError ? (
            <div className="error-state inline-error" role="alert">{data.riskError}</div>
          ) : data.riskAssessment ? (
            <>
              <div className="dashboard-risk-score">
                <strong>{data.riskAssessment.score === null ? "Score unavailable" : `${data.riskAssessment.score} / 100`}</strong>
                <span>{data.riskAssessment.recommendation}</span>
                <small>Confidence {data.riskAssessment.confidence_level} ({data.riskAssessment.confidence_percent}%) · Risk {data.riskAssessment.risk_level}</small>
              </div>
              <p className="data-provenance">{data.riskAssessment.exchange}:{data.riskAssessment.symbol} · {data.riskAssessment.source ?? "Historical source unavailable"} · as of {formatDate(data.riskAssessment.data_as_of)} · {data.riskAssessment.status}. Informational only, not financial advice.</p>
              {data.riskAssessment.top_factors[0] && <p className="muted">Top factor: {data.riskAssessment.top_factors[0].title} ({data.riskAssessment.top_factors[0].contribution > 0 ? "+" : ""}{data.riskAssessment.top_factors[0].contribution}) · {data.riskAssessment.top_factors[0].evidence}</p>}
              <Link className="text-link" href="/portfolio">View full “Why This Decision?” →</Link>
            </>
          ) : <div className="empty-state"><strong>No valued holding to assess</strong><p>Portfolio risk and the explainable meter require a valued holding with supported historical data.</p></div>}
        </article>

        <article className="section-card dashboard-watchlist-card">
          <div className="section-heading compact">
            <div><p className="eyebrow">WATCHLISTS</p><h2>Saved instruments</h2></div>
            <Link className="text-link" href="/watchlists">Open →</Link>
          </div>
          {loading ? <p role="status">Loading watchlists…</p> : !data.email ? (
            <p className="muted">Sign in to view your private watchlists.</p>
          ) : data.watchlistError ? (
            <div className="error-state inline-error" role="alert">{data.watchlistError}</div>
          ) : data.watchlists.length ? (
            <div className="dashboard-watchlists">
              {data.watchlists.map((watchlist) => (
                <div className="dashboard-watchlist" key={watchlist.id}>
                  <strong>{watchlist.name}</strong>
                  <span>{watchlist.instruments.length} saved</span>
                  {watchlist.instruments.map((item) => {
                    const performance = data.watchlistPerformance.find(
                      (entry) => entry.symbol === item.symbol && entry.exchange === item.exchange,
                    );
                    return (
                      <div className="dashboard-instrument" key={item.id}>
                        <span>{item.exchange}:{item.symbol}</span>
                        <small>
                          {performance?.period_return_percent === null ||
                          performance?.period_return_percent === undefined
                            ? performance?.error ?? "Historical performance unavailable"
                            : `${performance.period_return_percent >= 0 ? "+" : ""}${performance.period_return_percent.toFixed(2)}% historical return`}
                        </small>
                      </div>
                    );
                  })}
                  {!watchlist.instruments.length && <p className="muted">No symbols saved yet.</p>}
                </div>
              ))}
              <p className="data-provenance">Returns use available historical closes over the requested recent period; they are not live changes.</p>
            </div>
          ) : (
            <div className="empty-state"><strong>No watchlists</strong><p>Save instruments to follow their historical performance.</p></div>
          )}
        </article>

        <article className="section-card dashboard-alerts">
          <div className="section-heading compact">
            <div><p className="eyebrow">ALERTS</p><h2>Recent alert activity</h2></div>
            <Link className="text-link" href="/watchlists">Manage →</Link>
          </div>
          {loading ? <p role="status">Loading alert history…</p> : !data.email ? (
            <p className="muted">Sign in to view your private alert history.</p>
          ) : data.alertError ? (
            <div className="error-state inline-error" role="alert">{data.alertError}</div>
          ) : data.alerts.length ? (
            <ul className="dashboard-list">
              {data.alerts.map((alert) => (
                <li key={alert.id}>
                  <strong>{alert.message}</strong>
                  <small>{formatDate(alert.data_as_of)} · event recorded {formatDate(alert.created_at)}</small>
                </li>
              ))}
            </ul>
          ) : <div className="empty-state"><strong>No alert events</strong><p>No historical threshold events have been recorded.</p></div>}
          <p className="data-provenance">Events are recorded from historical bars. No email or push notification is delivered.</p>
        </article>

        <article className="section-card dashboard-activity">
          <div className="section-heading compact">
            <div><p className="eyebrow">RECENT ACTIVITY</p><h2>Workspace activity</h2></div>
            <Link className="text-link" href="/portfolio">Portfolio →</Link>
          </div>
          {loading ? <p role="status">Loading recent activity…</p> : !data.email ? (
            <p className="muted">Sign in to view private activity.</p>
          ) : recentActivity.length ? (
            <ul className="dashboard-list">
              {recentActivity.map((activity) => (
                <li key={`${activity.kind}-${activity.id}`}>
                  <strong>{activity.description}</strong>
                  <small>{activity.kind} · {formatDate(activity.date)}</small>
                </li>
              ))}
            </ul>
          ) : <div className="empty-state"><strong>No recent activity</strong><p>Portfolio transactions and alert events will appear here.</p></div>}
        </article>

        <article className="section-card dashboard-news">
          <div className="section-heading compact">
            <div><p className="eyebrow">NEWS HIGHLIGHTS</p><h2>Publisher headlines</h2></div>
            <Link className="text-link" href="/news">All news →</Link>
          </div>
          {loading && !data.news.length ? <p role="status">Loading headlines…</p> : data.newsError ? (
            <div className="error-state inline-error" role="alert">{data.newsError}</div>
          ) : data.news.length ? (
            <>
              <ul className="dashboard-list dashboard-news-list">
                {data.news.map((article) => (
                  <li key={article.source_id}>
                    <a href={article.url} rel="noreferrer" target="_blank">{article.headline}</a>
                    <small>{article.source} · {formatDate(article.published_at)}{article.related_symbols.length ? ` · ${article.related_symbols.join(", ")}` : ""}</small>
                  </li>
                ))}
              </ul>
              <p className="data-provenance">Source: {data.newsSource}. Headlines are publisher-linked; no generated summary is shown on this dashboard.</p>
            </>
          ) : <div className="empty-state"><strong>No publisher headlines</strong><p>The configured provider returned no articles.</p></div>}
        </article>
      </section>

      <section className="section-card">
        <div className="section-heading">
          <div><p className="eyebrow">WORKSPACE</p><h2>Explore FinSight</h2></div>
        </div>
        <div className="action-grid">
          <Link className="action-card" href="/screener"><span className="action-icon" aria-hidden="true">⌕</span><span><strong>Stock screener</strong><small>Filter supported instruments using historical data.</small></span><span className="action-arrow" aria-hidden="true">↗</span></Link>
          <Link className="action-card" href="/analysis"><span className="action-icon" aria-hidden="true">⌁</span><span><strong>Stock analysis</strong><small>Review historical performance, indicators, patterns, and research.</small></span><span className="action-arrow" aria-hidden="true">↗</span></Link>
          <Link className="action-card" href="/charts"><span className="action-icon" aria-hidden="true">◫</span><span><strong>Chart analysis</strong><small>Explore daily candles and technical overlays.</small></span><span className="action-arrow" aria-hidden="true">↗</span></Link>
          <Link className="action-card" href="/backtesting"><span className="action-icon" aria-hidden="true">↗</span><span><strong>Backtesting</strong><small>Simulate a strategy on available historical data.</small></span><span className="action-arrow" aria-hidden="true">↗</span></Link>
        </div>
      </section>
    </div>
  );
}
