# Implementation progress

Updated: 2026-10-20

## Completed and verified

- Inspected the workspace; it was empty before implementation.
- Added a Next.js App Router shell with responsive navigation and dashboard.
- Added a working frontend screener form connected to the FastAPI endpoint.
- Added a FastAPI health check, instrument lookup, and deterministic AND/OR screener filters.
- Clearly labeled all bundled instrument values as illustrative demo data.
- Added backend tests for health, filtering, invalid ranges, and missing instruments.
- Added local environment examples, a PostgreSQL Compose service definition, and setup documentation.
- Added SQLAlchemy 2.x models for users/sessions, instruments/candles, saved screens, portfolios/transactions, watchlists, backtests, news, alerts, and AI conversation metadata.
- Added Alembic schema migrations; `python -m alembic upgrade head` and `python -m alembic check` passed against local SQLite, including the portfolio-accounting migration.
- Added local SQLite persistence without Docker and PostgreSQL URL support.
- Added Argon2 password hashing, normalized email addresses, HTTP-only same-site cookie sessions, hashed random session tokens, expiry/revocation, origin checks, and an authentication rate limit.
- Added registration/login pages and owner-scoped saved-screen create/list/delete API routes.
- Added validated user-supplied daily CSV historical data provider, instrument search, OHLCV validation, duplicate detection, provenance/status, date filters, and bounded in-process caching.
- Added deterministic SMA, EMA, Wilder RSI, MACD, relative-volume and prior-range breakout calculations; daily historical indicator and pattern API routes.
- Added advanced historical screener with AND/OR, RSI/relative-volume/SMA/EMA/breakout conditions, matched-condition explanations, sorting, pagination, and saved-screen run support.
- Added a daily candlestick/volume SVG chart with indicator overlays, crosshair tooltip, date selection, RSI/MACD panels, and rule-explained breakout results.
- Added a reproducible two-template historical backtesting engine and UI with next-open execution, costs, slippage, stop/take-profit, equity curve, trade log, and ownership-bound persistence.
- Added owner-scoped portfolio CRUD for portfolios and transaction records, weighted-average cost accounting, cash validation, historical-close valuation, and aligned daily volatility/drawdown/correlation risk calculations.
- Added Finnhub financial-news API integration with server-only credentials, publisher links/timestamps, optional Gemini summaries grounded in returned headlines/excerpts, and explicit unavailable/no-article states.
- Added a responsive news page with optional provider-formatted ticker search, source-linked articles, an AI-summary action, and honest missing-credential messaging.
- Added owner-scoped watchlist CRUD and instrument management, configurable above/below historical-close alerts, enable/pause/delete lifecycle, read/unread alert history, cooldowns, and manual polling.
- Added an in-process single-instance polling scheduler, configurable interval, fresh/new-bar guards, historical source timestamps, per-bar database uniqueness, and skip reporting for missing symbol history. Alert events are never described as live-price notifications.
- Added an Alembic migration for alert-event bar timestamps and duplicate suppression; `python -m alembic upgrade head` and `python -m alembic check` passed.
- Added separate liveness and database-readiness health endpoints; readiness returns HTTP 503 with a non-sensitive message when the database query fails.
- Added responsive watchlist/alert workflows in the authenticated UI, including explicit historical-only warnings and a sign-in prompt for unauthenticated access.
- Added a deployment runbook covering production environment variables, migration release steps, single-process scheduler requirements, liveness/readiness probes, and an honest unverified checklist.
- `python -m pytest`: 55 tests passed, covering authentication, saved-screen/watchlist/alert user isolation, CSV validation, indicator math, breakout look-ahead behavior, backtest fills/costs, portfolio accounting, risk alignment, news-source validation, optional AI fallback, alert cooldowns, freshness, duplicate suppression, scheduler start/stop, and readiness failures.
- `python -m alembic check`: passed; no model/migration drift detected.
- `python -m compileall backend alembic`: passed.
- `npm run typecheck`: passed after the watchlist and news page changes.
- `npm run build`: passed; dashboard, screener, charts, backtesting, portfolio, news, watchlists, login, and registration routes prerendered.
- Local HTTP smoke test passed against separate production Next.js and FastAPI processes using a temporary migrated SQLite database: health, registration, private watchlist/item and alert create/list, explicit news-unavailable HTTP 503, and `/news` plus `/watchlists` HTTP 200. The temporary database and test servers were removed.

## Incomplete

- No licensed real-time/delayed exchange provider is integrated. Historical CSV provenance, rights, and corporate-action adjustments are not independently verified.
- Demo screener records remain in-memory and illustrative; historical quantitative endpoints use only configured CSV files.
- Only daily CSV bars are supported; no intraday data, VWAP, benchmark data, corporate-action adjustment, or financial fundamentals.
- Only the documented range-breakout pattern and two backtest templates are implemented; advanced custom strategies and performance-history reporting are pending.
- News and optional Gemini summaries are implemented but not externally verified because Finnhub/Gemini credentials are not configured; the wider Gemini assistant remains unimplemented.
- Watchlists, historical-bar alerts, alert history, and optional single-process polling are implemented. Email/push delivery, live-price alerting, multi-process scheduling, sector risk, and theme switching remain unimplemented.
- PostgreSQL is supported by configuration but not runtime-tested; no PostgreSQL service is available in the environment.
- Authentication rate limiting is in-process and not suitable as the only public-production control. Email verification, password reset, and session cleanup are pending.
- Production deployment, browser E2E tests, backups, monitoring, and public security hardening are not verified.
- Docker is not installed in the current environment, so PostgreSQL Compose cannot be started here.

## Verification and next work

- External configuration required for exchange data: select a licensed market-data provider, configure credentials and permitted usage/caching terms; user-owned CSV history is available for local development.
- External configuration required for production: PostgreSQL service, secure origins/cookies, secrets, hosting accounts, and monitoring/backup configuration.
- Next implementation task: deployment preparation is documented and local checks are complete. PostgreSQL runtime, provider-backed news/AI, hosted deployment, backups, and production security claims remain blocked until their services and credentials are available.
