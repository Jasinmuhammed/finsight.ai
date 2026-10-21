import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const navigation = read("../src/components/app-shell.tsx");
const analysisRoute = read("../src/app/analysis/page.tsx");
const chartRoute = read("../src/app/charts/page.tsx");
const historicalChart = read("../src/components/historical-chart.tsx");
const portfolio = read("../src/components/portfolio-workspace.tsx");
const riskReport = read("../src/components/risk-meter-report.tsx");
const riskTypes = read("../src/types/risk-meter.ts");
const riskApi = read("../backend/main.py");
const riskEngine = read("../backend/risk_meter.py");
const dashboard = read("../src/components/dashboard-workspace.tsx");
const screener = read("../src/app/screener/page.tsx");
const news = read("../src/components/news-workspace.tsx");
const watchlists = read("../src/components/watchlists-workspace.tsx");
const styles = read("../src/app/globals.css");

test("sidebar routes distinguish Stock Analysis and Chart Analysis", () => {
  assert.match(navigation, /label:\s*"Stock analysis",\s*href:\s*"\/analysis"/);
  assert.match(navigation, /label:\s*"Chart analysis",\s*href:\s*"\/charts"/);
});

test("analysis and chart routes select their focused presentation modes", () => {
  assert.match(analysisRoute, /<HistoricalChart mode="analysis"\s*\/>/);
  assert.match(chartRoute, /<HistoricalChart mode="chart"\s*\/>/);
  assert.match(chartRoute, /<h1>Chart analysis<\/h1>/);
});

test("analysis-only research, overview, and pattern details stay off the chart workspace", () => {
  assert.match(historicalChart, /mode === "analysis" && data && candles\.length > 0/);
  assert.match(historicalChart, /mode === "analysis" && <section className="section-card research-panel"/);
  assert.match(historicalChart, /mode === "analysis" && data && \(/);
  assert.match(historicalChart, /mode === "chart" && data\.patterns\.map/);
});

test("chart and analysis share the same historical data requests", () => {
  assert.match(historicalChart, /fetch\(`\$\{path\}\/candles/);
  assert.match(historicalChart, /fetch\(`\$\{path\}\/indicators/);
  assert.match(historicalChart, /fetch\(`\$\{path\}\/patterns/);
  assert.match(historicalChart, /new URLSearchParams\(window\.location\.search\)/);
});

test("chart workspace zoom keeps candles, indicator overlays, and tooltips on the same window", () => {
  assert.match(historicalChart, /Chart zoom controls/);
  assert.match(historicalChart, /Show all/);
  assert.match(historicalChart, /const chartCandles = candles\.slice\(firstVisibleIndex\)/);
  assert.match(historicalChart, /values\.slice\(firstVisibleIndex\)/);
  assert.match(historicalChart, /chartCandles\[hoverIndex\]/);
});

test("risk meter is deterministic, sourced, explained, and integrated into stock and portfolio analysis", () => {
  assert.match(riskApi, /"\/api\/v1\/risk-meter"/);
  assert.match(riskApi, /get_current_user/);
  assert.match(riskApi, /historical_freshness\(data_as_of\)/);
  assert.match(riskEngine, /BUY >=65, HOLD 36–64/);
  assert.match(riskEngine, /fewer than three core signals/);
  assert.match(historicalChart, /Calculate risk meter/);
  assert.match(historicalChart, /include_ai_explanation: includeAIExplanation/);
  assert.match(portfolio, /Largest holding risk meter/);
  assert.match(portfolio, /RiskMeterReport/);
  assert.match(riskReport, /Why This Decision\?/);
  assert.match(riskReport, /Bullish evidence/);
  assert.match(riskReport, /Bearish and risk evidence/);
  assert.match(riskReport, /What could change this assessment/);
  assert.match(riskReport, /Gemini.*cannot change the score or recommendation/);
  assert.match(riskTypes, /"SELL \/ REDUCE EXPOSURE"/);
});

test("risk-meter report timestamp formatter uses compatible Intl options", () => {
  assert.match(riskReport, /day:\s*"2-digit"[\s\S]*month:\s*"short"[\s\S]*year:\s*"numeric"[\s\S]*hour:\s*"2-digit"[\s\S]*minute:\s*"2-digit"/);
  assert.match(riskReport, /timeZone:\s*"Asia\/Kolkata"[\s\S]*timeZoneName:\s*"short"/);
  assert.doesNotMatch(riskReport, /dateStyle:|timeStyle:/);
});

test("dashboard uses configured APIs and explicitly leaves unsupported indices unavailable", () => {
  assert.match(dashboard, /getJson<ProviderStatus>\("\/market-data\/status"/);
  assert.match(dashboard, /getJson<\{ email: string \}>\("\/auth\/me"/);
  assert.match(dashboard, /credentials: "include"/);
  assert.match(dashboard, /No index data source is integrated/);
  assert.match(dashboard, /period_return_percent/);
  assert.match(dashboard, /Sign in to view your private portfolio/);
  assert.match(dashboard, /Search supported instruments/);
  assert.match(dashboard, /Watchlist historical returns/);
  assert.match(dashboard, /dashboard-sparkline/);
  assert.match(dashboard, /Largest valued holding/);
  assert.match(dashboard, /historical_last_close/);
  assert.match(dashboard, /historical provider data; unavailable prices are not estimated/);
  assert.match(dashboard, /not intraday\/live price changes/);
  assert.match(styles, /\.dashboard-grid \{ display: grid; grid-template-columns: repeat\(12/);
  assert.match(styles, /\.dashboard-sparkline path/);
});

test("screener uses only the configured historical screener, without illustrative demo rows", () => {
  assert.match(screener, /<AdvancedScreener/);
  assert.doesNotMatch(screener, /<Screener/);
  assert.match(screener, /validated daily historical data/);
});

test("news freshness and alert delivery copy reflect actual provider behavior", () => {
  assert.match(news, /Older than 7 days/);
  assert.match(news, /Publication time unavailable/);
  assert.match(news, /Gemini did not provide a summary/);
  assert.match(watchlists, /No email or push\s+notification is delivered/);
  assert.match(watchlists, /checks run in the API process/);
});

test("application-wide dark palette remains the default", () => {
  assert.match(styles, /color-scheme:\s*dark/);
  assert.match(styles, /--canvas:\s*#0b1118/);
  assert.match(styles, /--surface:\s*#111a24/);
  assert.match(styles, /\.candlestick-chart/);
  assert.match(styles, /\.pattern-overlay-marker/);
  assert.match(styles, /\.chart-zoom-controls/);
  assert.match(styles, /\.news-stale-tag/);
});
