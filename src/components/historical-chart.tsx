"use client";

import { FormEvent, PointerEvent, useEffect, useRef, useState } from "react";
import { RiskMeterReport } from "@/components/risk-meter-report";
import type { RiskMeterResponse } from "@/types/risk-meter";

type Candle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type Pattern = {
  name: string;
  detection_time: string;
  lookback_bars: number;
  prior_range_high: number;
  relative_volume: number | null;
  explanation: string;
  limitations: string[];
  conditions: { rule: string; passed: boolean; observed: number | null; threshold: number | null }[];
};

type ChartData = {
  candles: Candle[];
  indicators: Record<string, (number | null)[]>;
  patterns: Pattern[];
  source: string;
  dataStatus: string;
  freshnessStatus: string;
  dataAsOf: string | null;
  performance: {
    period_return_percent: number | null;
    annualized_volatility_percent: number | null;
    daily_return_observations: number;
    method: string;
  };
};

type ApiError = { detail?: string };
type Instrument = {
  symbol: string;
  exchange: "NSE" | "BSE";
  name: string;
};
type PortfolioOption = { id: string; name: string };

type ResearchResult = {
  symbol: string;
  exchange: "NSE" | "BSE";
  period: string;
  data: {
    status: "HISTORICAL" | "UNAVAILABLE" | "ERROR";
    source: string | null;
    freshness_status: string | null;
    data_as_of: string | null;
    candle_count: number;
    period_return_percent: number | null;
    annualized_volatility_percent: number | null;
    daily_return_observations: number;
    indicators: Record<string, number | null>;
    message: string | null;
  };
  news: {
    status: "AVAILABLE" | "NO_ARTICLES" | "UNAVAILABLE" | "ERROR";
    source: string | null;
    articles: {
      source: string;
      source_id: string;
      headline: string;
      summary: string;
      url: string;
      published_at: string;
      related_symbols: string[];
    }[];
    message: string | null;
  };
  ai: {
    status: "AVAILABLE" | "NOT_CONFIGURED" | "NO_SOURCES" | "ERROR";
    summary: string | null;
    message: string | null;
  };
  risk_considerations: string[];
  source_references: {
    kind: "HISTORICAL_DATA" | "NEWS";
    source: string;
    title: string;
    url: string | null;
    as_of: string | null;
  }[];
  limitations: string[];
};

type HistoricalChartMode = "analysis" | "chart";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const SVG_WIDTH = 960;
const PRICE_HEIGHT = 230;
const VOLUME_TOP = 265;
const VOLUME_HEIGHT = 65;

function linePoints(values: (number | null)[], xFor: (index: number) => number, yFor: (value: number) => number) {
  return values
    .map((value, index) => (value === null ? null : `${xFor(index)},${yFor(value)}`))
    .filter((point): point is string => point !== null)
    .join(" ");
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  });
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
    timeZoneName: "short",
  });
}

export function HistoricalChart({
  mode = "analysis",
}: {
  mode?: HistoricalChartMode;
}) {
  const chartRef = useRef<SVGSVGElement>(null);
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [searchMessage, setSearchMessage] = useState("");
  const [data, setData] = useState<ChartData | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [visibleBars, setVisibleBars] = useState(2000);
  const [showSma, setShowSma] = useState(true);
  const [showEma, setShowEma] = useState(false);
  const [showRsi, setShowRsi] = useState(false);
  const [showMacd, setShowMacd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [researchPeriod, setResearchPeriod] = useState("3M");
  const [research, setResearch] = useState<ResearchResult | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchError, setResearchError] = useState("");
  const [riskPeriod, setRiskPeriod] = useState<"1M" | "3M" | "6M" | "1Y">("3M");
  const [riskPortfolios, setRiskPortfolios] = useState<PortfolioOption[]>([]);
  const [riskPortfolioId, setRiskPortfolioId] = useState("");
  const [riskPortfolioError, setRiskPortfolioError] = useState("");
  const [riskAssessment, setRiskAssessment] = useState<RiskMeterResponse | null>(null);
  const [riskMeterLoading, setRiskMeterLoading] = useState(false);
  const [riskMeterError, setRiskMeterError] = useState("");

  useEffect(() => {
    if (mode !== "analysis") return;
    const controller = new AbortController();
    fetch(`${apiBase}/portfolios`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          if (response.status === 401) return [];
          throw new Error(`Portfolio list request failed (${response.status}).`);
        }
        return (await response.json()) as PortfolioOption[];
      })
      .then((portfolios) => {
        if (controller.signal.aborted) return;
        setRiskPortfolios(portfolios);
        setRiskPortfolioError("");
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) {
          setRiskPortfolioError(
            requestError instanceof Error
              ? requestError.message
              : "Portfolio choices are unavailable.",
          );
        }
      });
    return () => controller.abort();
  }, [mode]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedSymbol = params.get("symbol")?.trim().toUpperCase();
    const requestedExchange = params.get("exchange")?.toUpperCase();
    if (
      requestedSymbol &&
      /^[A-Z0-9][A-Z0-9._-]{0,31}$/.test(requestedSymbol) &&
      (requestedExchange === "NSE" || requestedExchange === "BSE")
    ) {
      setSymbol(requestedSymbol);
      setExchange(requestedExchange);
    }
  }, []);

  useEffect(() => {
    const query = symbol.trim();
    if (query.length < 2) {
      setInstruments([]);
      setSearchMessage("");
      return;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setSearchMessage("");
      try {
        const params = new URLSearchParams({ query, limit: "10" });
        const response = await fetch(
          `${apiBase}/market-data/instruments/search?${params}`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          const body = (await response.json()) as ApiError;
          throw new Error(body.detail || `Symbol search failed (${response.status}).`);
        }
        const results = (await response.json()) as Instrument[];
        setInstruments(results);
        setSearchMessage(
          results.length ? "" : "No matching symbols in the configured provider.",
        );
      } catch (requestError) {
        if (requestError instanceof Error && requestError.name !== "AbortError") {
          setInstruments([]);
          setSearchMessage(requestError.message);
        }
      }
    }, 250);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [symbol]);

  async function loadChart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanSymbol = symbol.trim().toUpperCase();
    if (!/^[A-Z0-9][A-Z0-9._-]{0,31}$/.test(cleanSymbol)) {
      setError("Enter a valid symbol using letters, numbers, dots, underscores, or hyphens.");
      setData(null);
      return;
    }
    if (startDate && endDate && startDate > endDate) {
      setError("The start date must be on or before the end date.");
      setData(null);
      return;
    }
    setLoading(true);
    setError("");
    setData(null);
    setHoverIndex(null);
    setVisibleBars(2000);

    const query = new URLSearchParams();
    if (startDate) query.set("start", startDate);
    if (endDate) query.set("end", endDate);
    query.set("limit", "2000");
    const path = `${apiBase}/market-data/instruments/${exchange}/${encodeURIComponent(cleanSymbol)}`;
    try {
      const [candleResponse, indicatorResponse, patternResponse] = await Promise.all([
        fetch(`${path}/candles?${query.toString()}`),
        fetch(`${path}/indicators?${query.toString()}&sma_period=20&ema_period=20&rsi_period=14`),
        fetch(`${path}/patterns?${query.toString()}&lookback=20&volume_multiplier=1.5`),
      ]);
      const responses = [candleResponse, indicatorResponse, patternResponse];
      for (const response of responses) {
        if (!response.ok) {
          const body = (await response.json()) as ApiError;
          throw new Error(body.detail || `Historical data request failed (${response.status}).`);
        }
      }
      const candles = (await candleResponse.json()) as {
        candles: Candle[];
        data_status: string;
        source: string;
        freshness_status: string;
        data_as_of: string | null;
      };
      const indicators = (await indicatorResponse.json()) as {
        indicators: Record<string, (number | null)[]>;
        performance: ChartData["performance"];
      };
      const patterns = (await patternResponse.json()) as { patterns: Pattern[] };
      setData({
        candles: candles.candles,
        indicators: indicators.indicators,
        patterns: patterns.patterns,
        source: candles.source,
        dataStatus: candles.data_status,
        freshnessStatus: candles.freshness_status,
        dataAsOf: candles.data_as_of,
        performance: indicators.performance,
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load historical candles.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function requestResearch() {
    const cleanSymbol = symbol.trim().toUpperCase();
    if (!/^[A-Z0-9][A-Z0-9._-]{0,31}$/.test(cleanSymbol)) {
      setResearch(null);
      setResearchError("Enter a valid symbol before requesting research.");
      return;
    }
    setResearch(null);
    setResearchError("");
    setResearchLoading(true);
    try {
      const response = await fetch(`${apiBase}/research`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: cleanSymbol,
          exchange,
          period: researchPeriod,
        }),
      });
      const payload = (await response.json()) as ResearchResult | ApiError;
      if (!response.ok) {
        throw new Error(
          "detail" in payload && payload.detail
            ? payload.detail
            : `Research request failed (${response.status}).`,
        );
      }
      if (!("data" in payload) || !("ai" in payload)) {
        throw new Error("The research service returned an invalid response.");
      }
      setResearch(payload);
    } catch (requestError) {
      setResearchError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load financial research.",
      );
    } finally {
      setResearchLoading(false);
    }
  }

  async function requestRiskMeter(includeAIExplanation = false) {
    const cleanSymbol = symbol.trim().toUpperCase();
    if (!/^[A-Z0-9][A-Z0-9._-]{0,31}$/.test(cleanSymbol)) {
      setRiskAssessment(null);
      setRiskMeterError("Enter a valid symbol before calculating the risk meter.");
      return;
    }
    setRiskMeterLoading(true);
    setRiskMeterError("");
    try {
      const response = await fetch(`${apiBase}/risk-meter`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: cleanSymbol,
          exchange,
          period: riskPeriod,
          ...(riskPortfolioId ? { portfolio_id: riskPortfolioId } : {}),
          include_ai_explanation: includeAIExplanation,
        }),
      });
      const payload = (await response.json()) as RiskMeterResponse | ApiError;
      if (!response.ok) {
        throw new Error(
          "detail" in payload && payload.detail
            ? payload.detail
            : `Risk meter request failed (${response.status}).`,
        );
      }
      setRiskAssessment(payload as RiskMeterResponse);
    } catch (requestError) {
      setRiskMeterError(
        requestError instanceof Error
          ? requestError.message
          : "Risk assessment could not be calculated.",
      );
    } finally {
      setRiskMeterLoading(false);
    }
  }

  const candles = data?.candles ?? [];
  const firstVisibleIndex = Math.max(0, candles.length - visibleBars);
  const chartCandles = candles.slice(firstVisibleIndex);
  const chartIndicators: Record<string, (number | null)[]> = Object.fromEntries(
    Object.entries(data?.indicators ?? {}).map(([name, values]) => [
      name,
      values.slice(firstVisibleIndex),
    ]),
  );
  const lows = chartCandles.map((candle) => candle.low);
  const highs = chartCandles.map((candle) => candle.high);
  const minimum = lows.length ? Math.min(...lows) : 0;
  const maximum = highs.length ? Math.max(...highs) : 1;
  const padding = (maximum - minimum) * 0.08 || maximum * 0.03;
  const priceMin = minimum - padding;
  const priceMax = maximum + padding;
  const plotWidth = SVG_WIDTH - 44;
  const xFor = (index: number) => 36 + ((index + 0.5) / Math.max(chartCandles.length, 1)) * plotWidth;
  const yForPrice = (value: number) =>
    12 + ((priceMax - value) / Math.max(priceMax - priceMin, Number.EPSILON)) * PRICE_HEIGHT;
  const maxVolume = Math.max(...chartCandles.map((candle) => candle.volume), 1);
  const rsi = data?.indicators.rsi ?? [];
  const macd = data?.indicators.macd ?? [];
  const macdSignal = data?.indicators.macd_signal ?? [];
  const chartRsi = chartIndicators.rsi ?? [];
  const chartMacd = chartIndicators.macd ?? [];
  const chartMacdSignal = chartIndicators.macd_signal ?? [];
  const macdValues = [...macd, ...macdSignal].filter(
    (value): value is number => value !== null,
  );
  const macdMinimum = macdValues.length ? Math.min(...macdValues) : -1;
  const macdMaximum = macdValues.length ? Math.max(...macdValues) : 1;
  const macdRange = Math.max(macdMaximum - macdMinimum, Number.EPSILON);
  const patternCandleIndices = new Set(
    (data?.patterns ?? [])
      .map((pattern) =>
        chartCandles.findIndex(
          (candle) => formatDate(candle.timestamp) === formatDate(pattern.detection_time),
        ),
      )
      .filter((index) => index >= 0),
  );

  function hover(event: PointerEvent<SVGSVGElement>) {
    if (!chartCandles.length || !chartRef.current) return;
    const rect = chartRef.current.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * SVG_WIDTH;
    const index = Math.floor(((x - 36) / plotWidth) * chartCandles.length);
    setHoverIndex(index >= 0 && index < chartCandles.length ? index : null);
  }

  function indicatorValues(index: number | null) {
    if (index === null || !data) return null;
    return {
      sma: chartIndicators.sma?.[index] ?? null,
      ema: chartIndicators.ema?.[index] ?? null,
      rsi: chartIndicators.rsi?.[index] ?? null,
      macd: chartIndicators.macd?.[index] ?? null,
    };
  }

  const hovered = hoverIndex === null ? null : chartCandles[hoverIndex];
  const hoveredIndicators = indicatorValues(hoverIndex);

  return (
    <div className="page-stack">
      <section className="section-card chart-controls">
        <form className="chart-form" onSubmit={loadChart}>
          <label className="field">
            <span>Symbol</span>
            <input
              autoCapitalize="characters"
              aria-autocomplete="list"
              list="market-instrument-suggestions"
              maxLength={32}
              onChange={(event) => {
                const selected = instruments.find(
                  (instrument) =>
                    instrument.symbol === event.target.value.trim().toUpperCase(),
                );
                if (selected) setExchange(selected.exchange);
                setResearch(null);
                setResearchError("");
                setRiskAssessment(null);
                setRiskMeterError("");
                setSymbol(event.target.value);
              }}
              placeholder="e.g. RELIANCE"
              value={symbol}
            />
            <datalist id="market-instrument-suggestions">
              {instruments.map((instrument) => (
                <option
                  key={`${instrument.exchange}:${instrument.symbol}`}
                  value={instrument.symbol}
                  label={`${instrument.exchange} · ${instrument.name}`}
                />
              ))}
            </datalist>
            {searchMessage && (
              <small className="symbol-search-message" role="status">
                {searchMessage}
              </small>
            )}
          </label>
          <label className="field">
            <span>Exchange</span>
            <select
              onChange={(event) => {
                setResearch(null);
                setResearchError("");
                setRiskAssessment(null);
                setRiskMeterError("");
                setExchange(event.target.value);
              }}
              value={exchange}
            >
              <option value="NSE">NSE</option>
              <option value="BSE">BSE</option>
            </select>
          </label>
          <label className="field">
            <span>From</span>
            <input onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} />
          </label>
          <label className="field">
            <span>To</span>
            <input onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} />
          </label>
          <button className="primary-button" disabled={loading} type="submit">
            {loading ? "Loading…" : "Load daily history"}
          </button>
        </form>
        <p className="data-provenance">
          Daily historical candles only; no live quotes. Data source and freshness are reported with the chart.
        </p>
      </section>

      {error && (
        <section className="section-card error-state" role="alert">
          <strong>Historical data unavailable</strong>
          <p>{error}</p>
          <p>Configure a supported historical-data provider in the API environment and retry.</p>
        </section>
      )}

      {mode === "analysis" && data && candles.length > 0 && (
        <section className="section-card stock-overview" aria-label={`${exchange}:${symbol.toUpperCase()} stock overview`}>
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">SELECTED INSTRUMENT</p>
              <h2>{exchange}:{symbol.toUpperCase()} overview</h2>
            </div>
            <span className="demo-tag historical-tag">Historical daily data · not a live quote</span>
          </div>
          <div className="analysis-metrics">
            <div><strong>Latest daily close</strong><span>{candles.at(-1)?.close.toFixed(2) ?? "Unavailable"}</span></div>
            <div><strong>Period return</strong><span>{data.performance.period_return_percent === null ? "Insufficient history" : `${data.performance.period_return_percent.toFixed(2)}%`}</span></div>
            <div>
              <strong>Annualized volatility</strong>
              <span>{data.performance.annualized_volatility_percent === null ? "Insufficient history" : `${data.performance.annualized_volatility_percent.toFixed(2)}%`}</span>
              <small>{data.performance.daily_return_observations} daily returns</small>
            </div>
            {[
              ["SMA 20", data.indicators.sma?.at(-1)],
              ["EMA 20", data.indicators.ema?.at(-1)],
              ["RSI 14", data.indicators.rsi?.at(-1)],
              ["MACD", data.indicators.macd?.at(-1)],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <strong>{label}</strong>
                <span>{typeof value === "number" ? value.toFixed(2) : "Insufficient history"}</span>
              </div>
            ))}
          </div>
          <p className="data-provenance">{data.performance.method} Returns and volatility are descriptive historical calculations, not a forecast or recommendation.</p>
        </section>
      )}

      {data && candles.length > 0 ? (
        <section className={`section-card chart-card ${mode === "chart" ? "chart-workspace" : ""}`}>
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">{exchange} · {symbol.toUpperCase()} · DAILY</p>
              <h2>Candlestick chart</h2>
            </div>
            <span className="demo-tag historical-tag">
              {data.dataStatus} · {data.freshnessStatus.replaceAll("_", " ")}
            </span>
          </div>
          <p className="data-provenance">
            {data.source} · Latest bar as of{" "}
            {data.dataAsOf ? formatTimestamp(data.dataAsOf) : "unknown"} · Historical data, not live.
          </p>
          {data.freshnessStatus === "STALE_HISTORY" && (
            <p className="provider-warning" role="status">
              Warning: this historical data is stale. Its latest bar is older than the recent-history window.
            </p>
          )}
          {data.freshnessStatus === "UNKNOWN" && (
            <p className="provider-warning" role="status">
              The freshness of this historical data could not be determined.
            </p>
          )}
          {mode === "analysis" && (
            <p className="data-provenance">{data.performance.method} Descriptive history, not a forecast or recommendation.</p>
          )}
          {mode === "chart" && (
            <div className="chart-zoom-controls" role="group" aria-label="Chart zoom controls">
              <span>Showing {chartCandles.length} of {candles.length} daily bars</span>
              <button
                className="secondary-button"
                disabled={chartCandles.length <= 20}
                onClick={() => {
                  setVisibleBars((current) =>
                    Math.max(20, Math.floor(Math.min(current, candles.length) / 2)),
                  );
                  setHoverIndex(null);
                }}
                type="button"
              >
                Zoom in
              </button>
              <button
                className="secondary-button"
                disabled={chartCandles.length >= candles.length}
                onClick={() => {
                  setVisibleBars((current) => Math.min(candles.length, current * 2));
                  setHoverIndex(null);
                }}
                type="button"
              >
                Zoom out
              </button>
              <button
                className="secondary-button"
                disabled={chartCandles.length >= candles.length}
                onClick={() => {
                  setVisibleBars(Math.max(candles.length, 1));
                  setHoverIndex(null);
                }}
                type="button"
              >
                Show all
              </button>
            </div>
          )}
          <div className="chart-toggles" aria-label="Chart indicators">
            <label><input checked={showSma} onChange={(event) => setShowSma(event.target.checked)} type="checkbox" /> SMA 20</label>
            <label><input checked={showEma} onChange={(event) => setShowEma(event.target.checked)} type="checkbox" /> EMA 20</label>
            <label><input checked={showRsi} onChange={(event) => setShowRsi(event.target.checked)} type="checkbox" /> RSI 14</label>
            <label><input checked={showMacd} onChange={(event) => setShowMacd(event.target.checked)} type="checkbox" /> MACD</label>
          </div>
          <div className="chart-scroll">
            <svg
              aria-label={`${exchange} ${symbol.toUpperCase()} historical daily candlestick chart with volume`}
              className="candlestick-chart"
              onPointerLeave={() => setHoverIndex(null)}
              onPointerMove={hover}
              ref={chartRef}
              role="img"
              viewBox={`0 0 ${SVG_WIDTH} 350`}
            >
              {[0, 1, 2, 3].map((line) => {
                const y = 12 + (PRICE_HEIGHT / 3) * line;
                const price = priceMax - ((priceMax - priceMin) / 3) * line;
                return (
                  <g key={line}>
                    <line className="chart-gridline" x1="36" x2={SVG_WIDTH} y1={y} y2={y} />
                    <text className="chart-axis-label" x="2" y={y + 4}>{price.toFixed(2)}</text>
                  </g>
                );
              })}
              {chartCandles.map((candle, index) => {
                const center = xFor(index);
                const barWidth = Math.max(2, Math.min(12, plotWidth / chartCandles.length * 0.62));
                const isUp = candle.close >= candle.open;
                const bodyTop = yForPrice(Math.max(candle.open, candle.close));
                const bodyBottom = yForPrice(Math.min(candle.open, candle.close));
                const height = Math.max(1, bodyBottom - bodyTop);
                const volumeHeight = candle.volume / maxVolume * VOLUME_HEIGHT;
                return (
                  <g key={`${candle.timestamp}-${index}`}>
                    <line
                      className={isUp ? "candle-wick up" : "candle-wick down"}
                      x1={center}
                      x2={center}
                      y1={yForPrice(candle.high)}
                      y2={yForPrice(candle.low)}
                    />
                    <rect
                      className={isUp ? "candle-body up" : "candle-body down"}
                      height={height}
                      width={barWidth}
                      x={center - barWidth / 2}
                      y={bodyTop}
                    />
                    <rect
                      className={isUp ? "volume-bar up" : "volume-bar down"}
                      height={volumeHeight}
                      width={barWidth}
                      x={center - barWidth / 2}
                      y={VOLUME_TOP + VOLUME_HEIGHT - volumeHeight}
                    />
                  </g>
                );
              })}
              {mode === "chart" && data.patterns.map((pattern, patternIndex) => {
                const candleIndex = chartCandles.findIndex(
                  (candle) =>
                    formatDate(candle.timestamp) === formatDate(pattern.detection_time),
                );
                if (candleIndex < 0) return null;
                const candle = chartCandles[candleIndex];
                return (
                  <g key={`${pattern.detection_time}-${patternIndex}`}>
                    <circle
                      className="pattern-overlay-marker"
                      cx={xFor(candleIndex)}
                      cy={Math.max(10, yForPrice(candle.high) - 9)}
                      r="4"
                    />
                    <title>{pattern.name} detected {formatDate(pattern.detection_time)} · rule-based pattern</title>
                  </g>
                );
              })}
              {showSma && chartIndicators.sma && (
                <polyline
                  className="indicator-line sma-line"
                  points={linePoints(chartIndicators.sma, xFor, yForPrice)}
                />
              )}
              {showEma && chartIndicators.ema && (
                <polyline
                  className="indicator-line ema-line"
                  points={linePoints(chartIndicators.ema, xFor, yForPrice)}
                />
              )}
              {hoverIndex !== null && (
                <line
                  className="chart-crosshair"
                  x1={xFor(hoverIndex)}
                  x2={xFor(hoverIndex)}
                  y1="8"
                  y2="340"
                />
              )}
              <line className="chart-volume-divider" x1="36" x2={SVG_WIDTH} y1={VOLUME_TOP} y2={VOLUME_TOP} />
              {chartCandles.filter((_, index) => index % Math.max(1, Math.ceil(chartCandles.length / 6)) === 0).map((candle) => {
                const index = chartCandles.indexOf(candle);
                return <text className="chart-axis-label" key={candle.timestamp} x={xFor(index)} y="347">{formatDate(candle.timestamp)}</text>;
              })}
            </svg>
          </div>
          <div className="chart-legend">
            <span><i className="legend-candle up" /> Up close</span>
            <span><i className="legend-candle down" /> Down close</span>
            {showSma && <span><i className="legend-line sma-line" /> SMA 20</span>}
            {showEma && <span><i className="legend-line ema-line" /> EMA 20</span>}
            {mode === "chart" && patternCandleIndices.size > 0 && (
              <span><i className="legend-pattern" /> Rule-based breakout</span>
            )}
            <span>Volume</span>
          </div>
          {(showRsi || showMacd) && (
            <div className="indicator-chart-panels">
              {showRsi && (
                <div className="indicator-panel">
                  <strong>RSI · 14</strong>
                  <svg
                    aria-label="Relative Strength Index, 14-day daily close calculation"
                    role="img"
                    viewBox={`0 0 ${SVG_WIDTH} 100`}
                  >
                    {[30, 50, 70].map((value) => {
                      const y = 8 + ((100 - value) / 100) * 72;
                      return <g key={value}><line className="chart-gridline" x1="36" x2={SVG_WIDTH} y1={y} y2={y} /><text className="chart-axis-label" x="8" y={y + 3}>{value}</text></g>;
                    })}
                    <polyline
                      className="indicator-line rsi-line"
                      points={linePoints(chartRsi, xFor, (value) => 8 + ((100 - value) / 100) * 72)}
                    />
                  </svg>
                </div>
              )}
              {showMacd && (
                <div className="indicator-panel">
                  <strong>MACD · 12, 26, 9</strong>
                  <svg
                    aria-label="Moving Average Convergence Divergence line and signal line"
                    role="img"
                    viewBox={`0 0 ${SVG_WIDTH} 100`}
                  >
                    <line
                      className="chart-gridline"
                      x1="36"
                      x2={SVG_WIDTH}
                      y1={8 + ((macdMaximum - 0) / macdRange) * 72}
                      y2={8 + ((macdMaximum - 0) / macdRange) * 72}
                    />
                    <polyline
                      className="indicator-line macd-line"
                      points={linePoints(chartMacd, xFor, (value) => 8 + ((macdMaximum - value) / macdRange) * 72)}
                    />
                    <polyline
                      className="indicator-line signal-line"
                      points={linePoints(chartMacdSignal, xFor, (value) => 8 + ((macdMaximum - value) / macdRange) * 72)}
                    />
                  </svg>
                </div>
              )}
            </div>
          )}
          {hovered && hoveredIndicators && (
            <div className="candle-tooltip" aria-live="polite">
              <strong>{formatDate(hovered.timestamp)}</strong>
              <span>O {hovered.open.toFixed(2)}</span><span>H {hovered.high.toFixed(2)}</span>
              <span>L {hovered.low.toFixed(2)}</span><span>C {hovered.close.toFixed(2)}</span>
              <span>Vol {hovered.volume.toLocaleString("en-IN")}</span>
              {showSma && <span>SMA {hoveredIndicators.sma?.toFixed(2) ?? "—"}</span>}
              {showEma && <span>EMA {hoveredIndicators.ema?.toFixed(2) ?? "—"}</span>}
              {showRsi && <span>RSI {hoveredIndicators.rsi?.toFixed(2) ?? "—"}</span>}
              {showMacd && <span>MACD {hoveredIndicators.macd?.toFixed(4) ?? "—"}</span>}
            </div>
          )}
          {(showRsi || showMacd) && (
            <div className="indicator-readouts">
              {showRsi && (
                <div>
                  <strong>RSI (14)</strong>
                  <span>{rsi.at(-1)?.toFixed(2) ?? "Not enough history"}</span>
                  <small>Wilder smoothing; based on daily closes.</small>
                </div>
              )}
              {showMacd && (
                <div>
                  <strong>MACD (12, 26, 9)</strong>
                  <span>{macd.at(-1)?.toFixed(4) ?? "Not enough history"}</span>
                  <small>EMA-based daily close calculation; intraday behavior is not inferred.</small>
                  <span>Signal {macdSignal.at(-1)?.toFixed(4) ?? "—"}</span>
                </div>
              )}
            </div>
          )}
          <p className="table-footnote">{data.source}. Candles are not exchange-verified.</p>
        </section>
      ) : data ? (
        <section className="section-card empty-state" role="status">
          <strong>No historical candles found</strong>
          <p>
            {data.source} returned no daily history for {exchange}:{symbol.toUpperCase()}
            {startDate || endDate
              ? ` in the selected date range${startDate ? ` from ${startDate}` : ""}${endDate ? ` through ${endDate}` : ""}.`
              : "."}
          </p>
          <p>Historical data only; no live quote is available.</p>
        </section>
      ) : (
        <section className="section-card empty-state">
          <span aria-hidden="true">⌁</span>
          <strong>Load historical candles to begin</strong>
          <p>No charts are generated from illustrative demo values.</p>
        </section>
      )}

      {mode === "analysis" && (
        <section className="section-card risk-meter-panel" aria-labelledby="risk-meter-heading">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">DETERMINISTIC INDICATOR SCORE</p>
              <h2 id="risk-meter-heading">Explainable risk-based meter</h2>
              <p className="muted">Informational historical assessment only; this never places or recommends an automatic trade.</p>
            </div>
            <span className="demo-tag">NOT FINANCIAL ADVICE</span>
          </div>
          <div className="research-request">
            <label className="field">
              <span>Scoring period</span>
              <select onChange={(event) => {
                setRiskPeriod(event.target.value as "1M" | "3M" | "6M" | "1Y");
                setRiskAssessment(null);
              }} value={riskPeriod}>
                <option value="1M">1 month</option>
                <option value="3M">3 months</option>
                <option value="6M">6 months</option>
                <option value="1Y">1 year</option>
              </select>
            </label>
            <label className="field">
              <span>Optional portfolio risk context</span>
              <select onChange={(event) => {
                setRiskPortfolioId(event.target.value);
                setRiskAssessment(null);
              }} value={riskPortfolioId}>
                <option value="">No portfolio context</option>
                {riskPortfolios.map((portfolio) => (
                  <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>
                ))}
              </select>
            </label>
            <button
              className="primary-button"
              disabled={riskMeterLoading || !symbol.trim()}
              onClick={() => void requestRiskMeter()}
              type="button"
            >
              {riskMeterLoading ? "Calculating…" : "Calculate risk meter"}
            </button>
          </div>
          {riskPortfolioError && <p className="muted" role="status">{riskPortfolioError}</p>}
          {riskMeterLoading && <p role="status">Calculating from validated daily historical data…</p>}
          {riskMeterError && (
            <div className="notice news-notice" role="alert">
              <strong>Risk assessment unavailable</strong>
              <p>{riskMeterError}</p>
              {riskMeterError.toLowerCase().includes("authentication") && (
                <a className="text-link" href="/login">Sign in to calculate this assessment.</a>
              )}
            </div>
          )}
          {riskAssessment && (
            <RiskMeterReport
              assessment={riskAssessment}
              explanationLoading={riskMeterLoading}
              onExplain={() => void requestRiskMeter(true)}
            />
          )}
        </section>
      )}

      {mode === "analysis" && <section className="section-card research-panel" aria-labelledby="research-heading">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">SOURCED RESEARCH</p>
            <h2 id="research-heading">AI financial research</h2>
            <p className="muted">
              Authenticated research from available historical data and linked publisher articles.
            </p>
          </div>
          <span className="demo-tag">NOT FINANCIAL ADVICE</span>
        </div>
        <div className="research-request">
          <label className="field">
            <span>Analysis period</span>
            <select
              onChange={(event) => {
                setResearch(null);
                setResearchError("");
                setResearchPeriod(event.target.value);
              }}
              value={researchPeriod}
            >
              <option value="1M">1 month</option>
              <option value="3M">3 months</option>
              <option value="6M">6 months</option>
              <option value="1Y">1 year</option>
            </select>
          </label>
          <button
            className="primary-button"
            disabled={researchLoading || !symbol.trim()}
            onClick={() => void requestResearch()}
            type="button"
          >
            {researchLoading ? "Researching…" : "Generate research"}
          </button>
        </div>
        {researchLoading && <p role="status">Loading historical data and available sources…</p>}
        {researchError && (
          <div className="notice news-notice" role="alert">
            <strong>Research unavailable</strong>
            <p>{researchError}</p>
            {researchError.toLowerCase().includes("authentication") && (
              <a className="text-link" href="/login">Sign in to request research.</a>
            )}
          </div>
        )}
        {research && (
          <div className="research-result">
            <div className="research-status-row" aria-label="Research source status">
              <span>Market data: {research.data.status}</span>
              <span>News: {research.news.status}</span>
              <span>AI: {research.ai.status}</span>
            </div>
            {research.data.message && <p role="status">{research.data.message}</p>}
            {research.news.message && <p role="status">{research.news.message}</p>}
            {research.data.status === "HISTORICAL" && (
              <>
                <h3>Historical observations · {research.symbol} · {research.period}</h3>
                <p className="data-provenance">
                  {research.data.source} · {research.data.candle_count} daily candles · as of{" "}
                  {research.data.data_as_of
                    ? formatTimestamp(research.data.data_as_of)
                    : "unknown"}{" "}
                  · {research.data.freshness_status?.replaceAll("_", " ")} · historical, not live.
                </p>
                <div className="analysis-metrics">
                  <div>
                    <strong>Period return · calculated</strong>
                    <span>
                      {research.data.period_return_percent === null
                        ? "Insufficient history"
                        : `${research.data.period_return_percent.toFixed(2)}%`}
                    </span>
                  </div>
                  <div>
                    <strong>Annualized volatility · calculated</strong>
                    <span>
                      {research.data.annualized_volatility_percent === null
                        ? "Insufficient history"
                        : `${research.data.annualized_volatility_percent.toFixed(2)}%`}
                    </span>
                    <small>{research.data.daily_return_observations} available close-to-close returns</small>
                  </div>
                  {Object.entries(research.data.indicators).map(([name, value]) => (
                    <div key={name}>
                      <strong>{name.replaceAll("_", " ").toUpperCase()} · calculated</strong>
                      <span>{value === null ? "Insufficient history" : value.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div className="research-ai">
              <h3>AI-generated explanation</h3>
              {research.ai.status === "AVAILABLE" && research.ai.summary ? (
                <p>{research.ai.summary}</p>
              ) : (
                <p role="status">
                  {research.ai.message ?? "No AI-generated explanation is available."}
                </p>
              )}
              <small>AI text is explanatory and may be wrong; verify it against the sources below.</small>
            </div>
            {research.news.articles.length > 0 && (
              <div>
                <h3>Publisher sources</h3>
                <ol className="research-article-list">
                  {research.news.articles.map((article, index) => (
                    <li key={article.source_id}>
                      <a href={article.url} rel="noreferrer" target="_blank">
                        [{index + 1}] {article.headline}
                      </a>
                      <span>{article.source} · {formatTimestamp(article.published_at)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {research.source_references.length > 0 && (
              <div>
                <h3>Source references</h3>
                <ul className="research-article-list">
                  {research.source_references.map((source, index) => (
                    <li key={`${source.kind}-${source.title}-${index}`}>
                      {source.url ? (
                        <a href={source.url} rel="noreferrer" target="_blank">{source.title}</a>
                      ) : (
                        <span>{source.title}</span>
                      )}
                      <span>{source.source}{source.as_of ? ` · ${formatTimestamp(source.as_of)}` : ""}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <h3>Risk considerations and limitations</h3>
              <ul className="research-limitations">
                {[...research.risk_considerations, ...research.limitations].map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </section>}

      {mode === "analysis" && data && (
        <section className="section-card">
          <div className="section-heading compact">
            <div><p className="eyebrow">RULE-BASED</p><h2>Range breakout patterns</h2></div>
            <span className="updated-label">{data.patterns.length} detected</span>
          </div>
          <p className="data-provenance">
            A setup is reported when a completed daily close exceeds the preceding 20-bar high.
            Volume confirmation is shown separately and is not a profitability signal.
          </p>
          {data.patterns.length ? (
            <div className="pattern-list">
              {data.patterns.map((pattern, index) => (
                <article className="pattern-item" key={`${pattern.detection_time}-${index}`}>
                  <div className="pattern-heading">
                    <strong>{pattern.name}</strong><span>{formatDate(pattern.detection_time)}</span>
                  </div>
                  <p>{pattern.explanation}</p>
                  <div className="pattern-conditions">
                    {pattern.conditions.map((condition) => (
                      <span className={condition.passed ? "condition-pass" : "condition-fail"} key={condition.rule}>
                        {condition.passed ? "Passed" : "Not met"} · {condition.rule}
                      </span>
                    ))}
                  </div>
                  <ul>{pattern.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state"><strong>No range breakouts found</strong><p>Try another instrument or historical period.</p></div>
          )}
        </section>
      )}
    </div>
  );
}
