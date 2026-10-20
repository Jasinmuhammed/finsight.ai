# FinSight AI

FinSight AI is a financial-intelligence application for Indian investors. This development build includes a responsive dashboard, authentication, advanced screening of imported daily history, technical indicators, charts, rule-based patterns, historical backtesting, portfolio accounting/risk, source-linked financial news, and authenticated watchlists/alerts.

> **Data notice:** The bundled `DEMO1`–`DEMO4` instruments and values are fabricated illustrative examples. They are not actual securities or market prices. No live market-data provider is configured. Financial news is a separate optional integration and is not market-price data.

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
7. Open `http://localhost:3000`. API documentation is at `http://localhost:8000/docs`.

Local development uses a persistent SQLite database (`finsight.db`) and does not require Docker. To use PostgreSQL, set `DATABASE_URL` in `.env`, for example `postgresql+psycopg://finsight:password@localhost:5432/finsight`, then apply migrations. A PostgreSQL service can optionally be started with `docker compose up -d db`.

### User-provided historical CSV data

The optional `csv` provider needs no paid API key. Set `MARKET_DATA_PROVIDER=csv` and `MARKET_DATA_CSV_DIR` to a directory of data that you are permitted to use. Name each daily file `NSE_SYMBOL.csv` or `BSE_SYMBOL.csv`; include the columns `Date,Open,High,Low,Close,Volume`. Date-only rows are interpreted at the 15:30 Asia/Kolkata session close. The app labels these records historical and user-supplied; it does not independently verify licensing, accuracy, adjustments, or provenance. No sample market candles are bundled.

The provider validates OHLCV values, rejects duplicate timestamps, limits CSV size and API result ranges, and keeps a short in-process cache. Intraday candles are not supported by this CSV adapter.

Create an account at `http://localhost:3000/register`. Passwords must be at least 12 characters. Authentication uses an HTTP-only, same-site session cookie. Set `SESSION_COOKIE_SECURE=true` when serving the API over HTTPS and restrict `AUTH_ALLOWED_ORIGINS` to your frontend origins in production.

### Financial news and optional AI summaries

Set `FINNHUB_API_KEY` in the API server environment to load Finnhub general news, or provider-specific ticker news by entering a Finnhub-formatted ticker. The page preserves publisher/source links and provider publication timestamps. Provider access, limits, attribution requirements, and permitted use depend on your Finnhub account and applicable terms. Without this key, the API reports news as unavailable; it does not display fabricated headlines.

To request an AI summary of the fetched article headlines and excerpts, also set `GEMINI_API_KEY` on the API server. `GEMINI_MODEL` defaults to `gemini-2.5-flash`. The key is sent only from the server to Google; generated summaries are instructed to use only the supplied source text and cite numbered source articles, which remain linked alongside the summary. If no Gemini key is configured, source articles remain available and the UI explicitly reports that AI summaries are unavailable. Gemini usage may have provider quotas or costs; no AI API is required for CSV-based quantitative analytics, screening, charts, backtests, or portfolio calculations.

### Watchlists and historical alerts

Sign in to create private watchlists and threshold alerts. Alert polling evaluates only newly timestamped daily candles from the configured user-supplied CSV provider, and skips bars older than four days; each event stores its source-bar timestamp and is deduplicated per alert/bar in the database. This is historical-data polling, not a live or delayed quote service. The API starts a single in-process scheduler using `ALERT_POLL_INTERVAL_SECONDS` (default 300; set to `0` to disable). Run a single API process when enabling it. Alerts with unavailable CSV files are not triggered. Events appear in the signed-in alert history; email, push, and other external notifications are not implemented.

## Verify

- Backend tests: `python -m pytest`
- Frontend type-check: `npm run typecheck`
- Production frontend build: `npm run build`

## Configuration and limitations

- `NEXT_PUBLIC_API_BASE_URL` configures the browser-to-API URL.
- `DATABASE_URL` defaults to local SQLite; PostgreSQL is also supported.
- `SESSION_COOKIE_SECURE`, `SESSION_TTL_HOURS`, and `AUTH_ALLOWED_ORIGINS` configure session cookies and browser-origin restrictions.
- `MARKET_DATA_PROVIDER` and `MARKET_DATA_CSV_DIR` enable user-supplied historical candles; there is no live/delayed exchange feed.
- `FINNHUB_API_KEY` enables the optional financial-news integration; provider data access and usage terms must be confirmed for your account.
- `GEMINI_API_KEY` and `GEMINI_MODEL` enable optional server-side article summaries; AI is not required for quantitative analytics.
- `ALERT_POLL_INTERVAL_SECONDS` controls the in-process historical alert polling interval in seconds; `0` disables the scheduler.
- The bundled `DEMO1`–`DEMO4` examples remain illustrative demo data. Quantitative charts, screening, and backtests operate only on explicitly configured user-supplied historical CSV files. Backtests are historical simulations, not predictions.
- Email/push alert delivery, live/delayed exchange data, multi-worker scheduling, and production deployment are not yet implemented or verified.
- Features not yet implemented are explicitly marked unavailable in navigation. See [docs/progress.md](./docs/progress.md) and [docs/implementation-plan.md](./docs/implementation-plan.md).
- Do not use this demo for investment decisions. It is not financial advice.

## Deployment

Deployment is not configured or verified. See the [deployment preparation runbook](./docs/deployment.md) for required settings, release sequencing, health checks, and limitations. PostgreSQL runtime, provider credentials, production security, and hosted smoke tests remain unverified. Do not deploy this build with real financial data until these checks are completed.
