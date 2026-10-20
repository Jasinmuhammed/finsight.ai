"use client";

import { FormEvent, PointerEvent, useRef, useState } from "react";

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
};

type ApiError = { detail?: string };

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

export function HistoricalChart() {
  const chartRef = useRef<SVGSVGElement>(null);
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [data, setData] = useState<ChartData | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [showSma, setShowSma] = useState(true);
  const [showEma, setShowEma] = useState(false);
  const [showRsi, setShowRsi] = useState(false);
  const [showMacd, setShowMacd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadChart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanSymbol = symbol.trim().toUpperCase();
    if (!cleanSymbol) {
      setError("Enter an instrument symbol to load its historical chart.");
      return;
    }
    setLoading(true);
    setError("");
    setData(null);
    setHoverIndex(null);

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
      };
      const indicators = (await indicatorResponse.json()) as {
        indicators: Record<string, (number | null)[]>;
      };
      const patterns = (await patternResponse.json()) as { patterns: Pattern[] };
      setData({
        candles: candles.candles,
        indicators: indicators.indicators,
        patterns: patterns.patterns,
        source: candles.source,
        dataStatus: candles.data_status,
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

  const candles = data?.candles ?? [];
  const lows = candles.map((candle) => candle.low);
  const highs = candles.map((candle) => candle.high);
  const minimum = lows.length ? Math.min(...lows) : 0;
  const maximum = highs.length ? Math.max(...highs) : 1;
  const padding = (maximum - minimum) * 0.08 || maximum * 0.03;
  const priceMin = minimum - padding;
  const priceMax = maximum + padding;
  const plotWidth = SVG_WIDTH - 44;
  const xFor = (index: number) => 36 + ((index + 0.5) / Math.max(candles.length, 1)) * plotWidth;
  const yForPrice = (value: number) =>
    12 + ((priceMax - value) / Math.max(priceMax - priceMin, Number.EPSILON)) * PRICE_HEIGHT;
  const maxVolume = Math.max(...candles.map((candle) => candle.volume), 1);
  const rsi = data?.indicators.rsi ?? [];
  const macd = data?.indicators.macd ?? [];
  const macdSignal = data?.indicators.macd_signal ?? [];
  const macdValues = [...macd, ...macdSignal].filter(
    (value): value is number => value !== null,
  );
  const macdMinimum = macdValues.length ? Math.min(...macdValues) : -1;
  const macdMaximum = macdValues.length ? Math.max(...macdValues) : 1;
  const macdRange = Math.max(macdMaximum - macdMinimum, Number.EPSILON);

  function hover(event: PointerEvent<SVGSVGElement>) {
    if (!candles.length || !chartRef.current) return;
    const rect = chartRef.current.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * SVG_WIDTH;
    const index = Math.floor(((x - 36) / plotWidth) * candles.length);
    setHoverIndex(index >= 0 && index < candles.length ? index : null);
  }

  function indicatorValues(index: number | null) {
    if (index === null || !data) return null;
    return {
      sma: data.indicators.sma[index],
      ema: data.indicators.ema[index],
      rsi: data.indicators.rsi[index],
      macd: data.indicators.macd[index],
    };
  }

  const hovered = hoverIndex === null ? null : candles[hoverIndex];
  const hoveredIndicators = indicatorValues(hoverIndex);

  return (
    <div className="page-stack">
      <section className="section-card chart-controls">
        <form className="chart-form" onSubmit={loadChart}>
          <label className="field">
            <span>Symbol</span>
            <input
              autoCapitalize="characters"
              maxLength={32}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="e.g. RELIANCE"
              value={symbol}
            />
          </label>
          <label className="field">
            <span>Exchange</span>
            <select onChange={(event) => setExchange(event.target.value)} value={exchange}>
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
          Daily candles only. The chart displays historical user-supplied CSV data; it is not a live feed.
        </p>
      </section>

      {error && (
        <section className="section-card error-state" role="alert">
          <strong>Historical data unavailable</strong>
          <p>{error}</p>
          <p>Configure a permitted CSV source in the API environment and retry.</p>
        </section>
      )}

      {data && candles.length > 0 ? (
        <section className="section-card chart-card">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">{exchange} · {symbol.toUpperCase()} · DAILY</p>
              <h2>Candlestick chart</h2>
            </div>
            <span className="demo-tag historical-tag">{data.dataStatus}</span>
          </div>
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
              {candles.map((candle, index) => {
                const center = xFor(index);
                const barWidth = Math.max(2, Math.min(12, plotWidth / candles.length * 0.62));
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
              {showSma && data.indicators.sma && (
                <polyline
                  className="indicator-line sma-line"
                  points={linePoints(data.indicators.sma, xFor, yForPrice)}
                />
              )}
              {showEma && data.indicators.ema && (
                <polyline
                  className="indicator-line ema-line"
                  points={linePoints(data.indicators.ema, xFor, yForPrice)}
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
              {candles.filter((_, index) => index % Math.max(1, Math.ceil(candles.length / 6)) === 0).map((candle) => {
                const index = candles.indexOf(candle);
                return <text className="chart-axis-label" key={candle.timestamp} x={xFor(index)} y="347">{formatDate(candle.timestamp)}</text>;
              })}
            </svg>
          </div>
          <div className="chart-legend">
            <span><i className="legend-candle up" /> Up close</span>
            <span><i className="legend-candle down" /> Down close</span>
            {showSma && <span><i className="legend-line sma-line" /> SMA 20</span>}
            {showEma && <span><i className="legend-line ema-line" /> EMA 20</span>}
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
                      points={linePoints(rsi, xFor, (value) => 8 + ((100 - value) / 100) * 72)}
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
                      points={linePoints(macd, xFor, (value) => 8 + ((macdMaximum - value) / macdRange) * 72)}
                    />
                    <polyline
                      className="indicator-line signal-line"
                      points={linePoints(macdSignal, xFor, (value) => 8 + ((macdMaximum - value) / macdRange) * 72)}
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
        <section className="section-card empty-state">
          <strong>No daily candles in the selected range</strong>
          <p>Adjust the symbol or historical date range.</p>
        </section>
      ) : (
        <section className="section-card empty-state">
          <span aria-hidden="true">⌁</span>
          <strong>Load historical candles to begin</strong>
          <p>No charts are generated from illustrative demo values.</p>
        </section>
      )}

      {data && (
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
