# FinSight AI

FinSight AI is a financial-intelligence application for Indian investors. This development build includes a responsive dashboard, authentication, advanced screening of imported daily history, technical indicators, charts, rule-based patterns, historical backtesting, portfolio accounting/risk, source-linked financial news, and authenticated watchlists/alerts.

> **Data notice:** The bundled `DEMO1`–`DEMO4` instruments and values are fabricated illustrative examples. They are not actual securities or market prices. No live-quote provider is configured. Finnhub and Yahoo Finance can optionally provide daily historical candles; these are never represented as live quotes. Financial news is a separate optional integration and is not market-price data.

## Requirements

- Node.js 20.9 or newer
- Python 3.12 or newer
- SQLite is included with Python. Docker Compose is optional for PostgreSQL.

## Run locally

1. Copy `.env.example` to `.env`. This file configures both the API and Next.js.
2. Install frontend dependencies: `npm install`
3. Install backend dependencies: `python -m pip install -r requirements.txt`
4. Apply database migrations: `python -m alembic upgrade head`
5. Start the API in one terminal: `python -m uvicorn backend.main:app --reload --port 8000`
6. Start the frontend in another terminal: `npm run dev`
7. Open `http://localhost:3000` or `http://127.0.0.1:3000`. API documentation is at `http://localhost:8000/docs`.

Local development uses a persistent SQLite database (`finsight.db`) and does not require Docker. To use PostgreSQL, set `DATABASE_URL` in `.env`, for example `postgresql+psycopg://finsight:password@localhost:5432/finsight`, then apply migrations. A PostgreSQL service can optionally be started with `docker compose up -d db`.

### User-provided historical CSV data

The optional `csv` provider needs no paid API key. Set `MARKET_DATA_PROVIDER=csv` and `MARKET_DATA_CSV_DIR` to a directory of data that you are permitted to use. Name each daily file `NSE_SYMBOL.csv` or `BSE_SYMBOL.csv`; include the columns `Date,Open,High,Low,Close,Volume`. Date-only rows are interpreted at the 15:30 Asia/Kolkata session close. Timestamped rows must include a timezone when they are not date-only. Rows must be chronological, and only one daily bar per Asia/Kolkata market date is accepted. The app labels these records historical and user-supplied; it does not independently verify licensing, accuracy, adjustments, or provenance. No sample market candles are bundled.

The provider validates required columns, numeric/finite OHLCV values, OHLC bounds, duplicates, row order, and market-date uniqueness; invalid rows return an API validation error instead of being reordered or silently skipped. API date filters use Asia/Kolkata market dates. CSV files are cached in-process for five minutes, with file modification times used to invalidate candle entries. There is no automatic fallback between Finnhub and CSV: select the intended source explicitly. When the selected provider is unavailable, the API/UI reports that state and does not substitute illustrative demo values. Intraday candles are not supported by this CSV adapter.

### Optional Finnhub historical candles

The app can request daily historical bars from Finnhub using its [`stock/candle` endpoint](https://finnhub.io/docs/api/stock-candles) at daily resolution, the [symbol-search endpoint](https://finnhub.io/docs/api/symbol-search), and [symbol-list endpoint](https://finnhub.io/docs/api/stock-symbols); it does not call a quote or real-time endpoint. To configure locally, copy `.env.example` to `.env`, then set `MARKET_DATA_PROVIDER=finnhub` and `FINNHUB_API_KEY=<your key>` there and restart the API. The key is read by the backend only; never put it in a `NEXT_PUBLIC_*` variable, frontend code, or browser request. `FINNHUB_SYMBOLS` defines the bounded whole-universe screener list in `EXCHANGE:SYMBOL` format, for example `NSE:RELIANCE,NSE:TCS`. It is also an explicit exchange-qualified source for chart search: matching configured tickers appear even if Finnhub's search response is empty, and an unprefixed Finnhub result is assigned an exchange only when it uniquely matches a configured ticker. The app retains the exact Finnhub `symbol` returned by symbol search for the subsequent candle request rather than reconstructing a provider symbol from the app's exchange-qualified identifier. If conflicting provider symbols map to one internal instrument, it does not guess which identifier to request. Finnhub's symbol-search response fields (`symbol`, `displaySymbol`, `description`, and `type`) do not by themselves establish NSE/BSE exchange; the adapter does not guess an exchange for unconfigured or ambiguous symbols. Search filtering is not proof that the selected instrument is available to your Finnhub account.

Finnhub publishes [plan information](https://finnhub.io/pricing), but exchange coverage, endpoint entitlement, historical depth, and limits are account/plan-dependent and may change. The public documentation/pricing view alone does not establish that a particular NSE/BSE instrument or daily-history request is available on a given account. A local authenticated smoke test found that both the app's reconstructed exchange-prefixed candle symbol and Finnhub's exact unprefixed search-result symbol received upstream HTTP 403 for daily candles. The search endpoint returned a matching symbol, but this does not verify candle endpoint entitlement; check the current terms and account access in Finnhub before relying on historical data. No candle data was returned or represented as available.

Finnhub candles are validated, limited to 5,000 bars and a 20-year requested range, and cached in-process for five minutes. Responses retain provider UTC timestamps and identify their source as daily historical data. The UI reports an as-of timestamp in Asia/Kolkata and marks data beyond the four-calendar-day recent-history heuristic as stale; neither label implies live prices or guarantees market-session availability. API failures, missing keys, denied endpoint access, and rate limits are surfaced rather than replaced with demo values. For key-free local development, explicitly select and use the user-supplied CSV workflow above.

After configuring the key and restarting the API, verify your account using `/api/v1/market-data/status`, then `/api/v1/market-data/instruments/search?query=RELIANCE`, and finally a bounded request such as `/api/v1/market-data/instruments/NSE/RELIANCE/candles?start=2025-01-01&end=2025-01-31`. Use only an instrument returned by the authenticated search; HTTP errors or `UNAVAILABLE` are not evidence that the adapter has fabricated data.

### Optional Yahoo Finance historical candles

The optional `yahoo` provider uses the `yfinance` library and needs no API key. Select it explicitly by setting `MARKET_DATA_PROVIDER=yahoo` for the backend and restarting the API. Only these verified NSE mappings are supported: `RELIANCE` → `RELIANCE.NS`, `TCS` → `TCS.NS`, and `INFY` → `INFY.NS`. Instrument search exposes only this mapped universe; unsupported symbols and BSE instruments are rejected instead of guessed.

The adapter requests daily history, disables auto-adjustment, validates OHLCV values and timezone-aware chronological timestamps, and caches results in-process for five minutes. Empty upstream history remains an empty result; errors are not replaced by data from another provider. Responses identify Yahoo Finance as the source and historical candles as the data type, never live quotes. No CSV, Finnhub, or demo fallback occurs when Yahoo is selected.

`yfinance` is an unofficial client for Yahoo Finance's public APIs and is not affiliated with Yahoo. Yahoo data availability, coverage, corrections, request limits, licensing, and terms may change; check that your intended use is permitted. Automated tests mock the yfinance interface and do not establish live availability through FinSight AI. Verify a configured instance using `/api/v1/market-data/status`, `/api/v1/market-data/instruments/search?query=RELIANCE`, and `/api/v1/market-data/instruments/NSE/RELIANCE/candles?start=2025-01-01&end=2025-01-31`.

### Stock analysis

Open **Stock analysis** to search the configured provider, select NSE or BSE, and request bounded daily history. The page displays historical candles, volume, selectable SMA/EMA/RSI/MACD overlays, look-ahead-safe historical range breakouts, source/freshness/as-of metadata, and descriptive period return and annualized volatility. SMA is a trailing arithmetic mean; EMA uses an initial SMA seed and alpha `2/(period+1)`; RSI uses Wilder smoothing; MACD uses seeded 12/26 EMAs and a 9-period EMA signal. Indicator warm-up positions are null and the UI labels them insufficient history. Period return is the first-to-last close return; volatility is the sample standard deviation (`n-1`) of consecutive available close-to-close simple returns, annualized with `sqrt(252)`. Missing sessions are not filled or imputed; a return across a data gap remains one observation, so the annualization does not correct for missing bars. Calculations do not adjust for dividends or corporate actions and are not investment advice.

Symbol search and candles require a configured provider. An unavailable provider is shown as unavailable; illustrative screener examples are never used to populate the chart. To reproduce locally with CSV, configure the CSV provider as described above, place permitted files such as `NSE_RELIANCE.csv` in the configured directory, then open `http://localhost:3000/analysis`. The historical chart workflow has been browser-checked for the unavailable-provider, invalid-symbol, and reversed-date states. A real chart cannot be verified until a permitted historical provider or CSV is configured.

#### Authenticated AI research

The analysis page includes a signed-in research request for the selected symbol and a bounded period (`1M`, `3M`, `6M`, or `1Y`). The API reuses configured daily history and the existing indicator/performance calculations, then attempts to retrieve Finnhub company news using the exchange-prefixed symbol. Historical observations, news results, AI-generated explanation, source links/timestamps, risk considerations, and limitations are returned as separate fields. Missing or failed sources remain unavailable/error states; no values or articles are fabricated. If sources exist but Gemini is not configured, the UI shows the sourced metrics/articles and states that no AI explanation was produced; there is no AI-shaped deterministic fallback.

To configure locally, create/edit `.env` in the project root (the same directory as `.env.example`), set `GEMINI_API_KEY` there, and restart the API. `GEMINI_MODEL` is optional and currently defaults to `gemini-2.5-flash` in `.env.example` and the backend; keep that configured value unless you have verified another model is supported for your account. Never paste the key into frontend files, a `NEXT_PUBLIC_*` variable, issue/chat messages, or logs. `.env` is covered by `.gitignore`; only `.env.example` is meant to be tracked. The API loads the root `.env` via `python-dotenv` during backend startup, while the Gemini integration reads the configured value server-side when a request is handled.

For an end-to-end smoke test, also configure at least one permitted research source: Finnhub historical data/news with `MARKET_DATA_PROVIDER=finnhub` and `FINNHUB_API_KEY`, or a user-owned daily CSV with `MARKET_DATA_PROVIDER=csv` and `MARKET_DATA_CSV_DIR`. Restart the API after changing `.env`, sign in at `http://localhost:3000`, open **Stock analysis**, select a supported symbol/exchange and period, and click **Generate research**. A successful real Gemini call is shown as `AI: AVAILABLE` with an explanation; assess market-data and news statuses independently (`HISTORICAL`/`AVAILABLE` versus `UNAVAILABLE`/`ERROR`). `AI: AVAILABLE` alone does not prove that a live market-data or news provider returned information; inspect the returned source labels, timestamps, and linked articles. With no configured sources the endpoint reports `NO_SOURCES` and does not call Gemini.

Research requires an authenticated session, checks the request origin, and is limited to five requests per user per minute per API process. Article headlines/excerpts are treated as untrusted source data in the Gemini prompt; generated statements are presented as potentially incorrect and must be checked against the linked sources. The endpoint does not accept arbitrary prompt text. This workspace's `.env` and provider keys are not configured, so a live Gemini/research smoke test has not been performed here.

Create an account at `http://localhost:3000/register`. Passwords must be at least 12 characters. Authentication uses an HTTP-only, same-site session cookie. Set `SESSION_COOKIE_SECURE=true` when serving the API over HTTPS and restrict `AUTH_ALLOWED_ORIGINS` to your frontend origins in production.

### Portfolio accounting

Create a portfolio with starting cash, then record each purchase or sale with symbol, exchange, quantity, execution price, transaction charges, and date/time. Transactions persist in the authenticated user's portfolio ledger. The ledger uses **weighted-average cost**: each buy adds its gross value and buy charges to open cost basis; a partial sale removes the sold quantity at the current weighted-average cost; realized P&L is sale proceeds minus that cost basis and the sale charges. Cash is reduced by buy value plus charges and increased by sale proceeds net of charges. Holdings' average buy price includes allocated buy charges, and invested capital is the remaining cost basis of open holdings. A full sale closes the holding; later purchases begin a new weighted-average basis. Dividends, taxes beyond entered charges, and corporate actions are not modeled.

Portfolio current values are calculated only from the configured provider's last validated daily close, with source, timestamp, and freshness shown; they are historical, not live quotes. If a holding has no usable history or the provider fails, its price, value, and unrealized P&L remain unavailable and the portfolio total is marked incomplete. Stale historical closes remain identified as stale and should not be treated as current valuation.

### Financial news and optional AI summaries

Set `FINNHUB_API_KEY` in the API server environment to load Finnhub general news, or provider-specific ticker news by entering a Finnhub-formatted ticker. The page preserves publisher/source links and provider publication timestamps. Provider access, limits, attribution requirements, and permitted use depend on your Finnhub account and applicable terms. Without this key, the API reports news as unavailable; it does not display fabricated headlines.

To request an AI summary of the fetched article headlines and excerpts, also set `GEMINI_API_KEY` on the API server. `GEMINI_MODEL` defaults to `gemini-2.5-flash`. The key is sent only from the server to Google; generated summaries are instructed to use only the supplied source text and cite numbered source articles, which remain linked alongside the summary. If no Gemini key is configured, source articles remain available and the UI explicitly reports that AI summaries are unavailable. Gemini usage may have provider quotas or costs; no AI API is required for CSV-based quantitative analytics, screening, charts, backtests, or portfolio calculations.

### Watchlists and historical alerts

Sign in to create private watchlists and threshold alerts. Alert polling evaluates only newly timestamped daily candles from the configured user-supplied CSV provider, and skips bars older than four days; each event stores its source-bar timestamp and is deduplicated per alert/bar in the database. This is historical-data polling, not a live or delayed quote service. The API starts a single in-process scheduler using `ALERT_POLL_INTERVAL_SECONDS` (default 300; set to `0` to disable). Run a single API process when enabling it. Alerts with unavailable CSV files are not triggered. Events appear in the signed-in alert history; email, push, and other external notifications are not implemented.

## Verify

- Backend tests: `python -m pytest`
- Frontend tests: `npm run test`
- Next.js development-origin regression test: `npm run test:config`
- Frontend type-check: `npm run typecheck`
- Production frontend build: `npm run build`

## Configuration and limitations

- `NEXT_PUBLIC_API_BASE_URL` configures the browser-to-API URL.
- `DATABASE_URL` defaults to local SQLite; PostgreSQL is also supported.
- `SESSION_COOKIE_SECURE`, `SESSION_TTL_HOURS`, and `AUTH_ALLOWED_ORIGINS` configure session cookies and browser-origin restrictions.
- `MARKET_DATA_PROVIDER=csv` and `MARKET_DATA_CSV_DIR` enable user-supplied historical candles. `MARKET_DATA_PROVIDER=finnhub`, `FINNHUB_API_KEY`, and `FINNHUB_SYMBOLS` enable Finnhub daily historical candles and a configured NSE/BSE screener universe. `MARKET_DATA_PROVIDER=yahoo` enables the explicitly mapped Yahoo Finance daily historical candles. None of these providers supplies live quotes in this application.
- `FINNHUB_API_KEY` enables the optional financial-news integration; provider data access and usage terms must be confirmed for your account.
- `GEMINI_API_KEY` and `GEMINI_MODEL` enable optional server-side article summaries; AI is not required for quantitative analytics.
- `GEMINI_API_KEY` and `GEMINI_MODEL` also enable the authenticated stock-research explanation on `/analysis`. Keep both on the server; no key belongs in `NEXT_PUBLIC_*` variables.
- `ALERT_POLL_INTERVAL_SECONDS` controls the in-process historical alert polling interval in seconds; `0` disables the scheduler.
- The bundled `DEMO1`–`DEMO4` examples remain illustrative demo data. Quantitative charts, screening, and backtests operate only on explicitly configured historical providers or user-supplied historical CSV files. Backtests are historical simulations, not predictions.
- Email/push alert delivery, live/delayed exchange data, multi-worker scheduling, and production deployment are not yet implemented or verified.
- Features not yet implemented are explicitly marked unavailable in navigation. See [docs/progress.md](./docs/progress.md) and [docs/implementation-plan.md](./docs/implementation-plan.md).
- Do not use this demo for investment decisions. It is not financial advice.

## Deployment

Deployment is not configured or verified. See the [deployment preparation runbook](./docs/deployment.md) for required settings, release sequencing, health checks, and limitations. PostgreSQL runtime, provider credentials, production security, and hosted smoke tests remain unverified. Do not deploy this build with real financial data until these checks are completed.
