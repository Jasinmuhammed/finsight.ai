# Implementation plan

## Milestones and acceptance criteria

1. **Foundation** — Create a Next.js App Router frontend, FastAPI API, local service configuration, health endpoint, and runnable instructions. Verify backend tests and frontend type-check/build.
2. **UI and navigation** — Deliver an accessible responsive shell, working navigation for implemented pages, and clear disabled states for unfinished areas.
3. **Authentication and database** — Add secure registration/session flows, PostgreSQL models and migrations, and user-isolation tests.
4. **Market data** — Select a licensed provider, implement validated provider adapters, caching and freshness metadata; no credentials or live provider are currently configured.
5. **Screener and indicators** — Add validated AND/OR filters, persistence, tested indicators, and paginated results using supported data.
6. **Charts and patterns** — Add historical charts and explainable, look-ahead-safe pattern rules.
7. **Backtesting** — Add deterministic strategy execution, costs, reporting, and tests for timing and bias.
8. **Portfolio and risk** — Add transaction accounting, ownership authorization, performance, and aligned risk metrics.
9. **News and AI** — Integrate permitted news and backend-only Gemini explanations grounded in validated data.
10. **Watchlists and alerts** — Add persistent lists, alert lifecycle, cooldowns, and a single-instance scheduler.
11. **Quality assurance** — Run automated and browser tests, resolve critical failures, and document limitations.
12. **Deployment and documentation** — Prepare and verify hosted services when credentials and hosting access are provided.

## Acceptance gate

The product is complete only after the relevant application workflows, security controls, tests, data provenance, and deployment status have been verified. Do not treat disabled navigation, illustrative data, or scaffolding as complete functionality.

## Current milestone state

- **Foundation and initial UI:** implemented; local API and frontend builds have been verified.
- **Authentication and database:** implemented with SQLite/PostgreSQL SQLAlchemy models, Alembic migration, Argon2 password hashing, revocable HTTP-only sessions, owner-scoped saved screens, and sign-in/register pages. PostgreSQL runtime is not verified because no PostgreSQL service is available.
- **Market data:** provider protocol, validated user-supplied daily CSV adapter, caching, date filtering, instrument search, provenance notes, and explicit unavailable status are implemented. No licensed vendor feed is integrated or configured; CSV rights and accuracy remain the user's responsibility.
- **Screener, indicators, charts, and patterns:** historical screener, AND/OR rules, pagination/sorting, saved screens, SMA/EMA/RSI/MACD/relative volume, daily volume/candlestick SVG chart, and explainable historical range breakouts are implemented. Only one documented pattern rule is currently available.
- **Backtesting:** two reproducible daily strategies, next-open execution, fees/slippage, stop/take-profit, position sizing, trade log, equity curve, and performance metrics are implemented and tested. Corporate actions, taxes, and benchmark comparison are not modeled.
- **Portfolio and risk:** user-isolated portfolios, starting cash, editable transactions, weighted-average cost accounting, historical-close valuation, aligned-return volatility/drawdown/correlation, and allocation summaries are implemented. Sector data and performance history are not available.
- **News/AI:** Finnhub source-linked news API and page plus optional backend-only Gemini summaries are implemented and covered with mocked provider tests. Live provider/API behavior remains unverified until credentials are configured; provider terms, limits, and attribution need deployment review. The general Gemini assistant is pending.
- **Watchlists/alerts:** private CRUD, configurable threshold rules, cooldowns, read/unread history, daily-history freshness guards, per-bar database deduplication, manual polling, and a single-process configurable scheduler are implemented. Alerts operate only on user-supplied historical CSV bars; no live-price or email/push notification service is provided.
- **Quality assurance:** 55 backend tests, TypeScript type-check, production build, Python compilation, SQLite migrations/model parity, database-readiness failure handling, and a local HTTP smoke test for authenticated watchlists/alerts, explicit provider-unavailable news, and frontend routes have passed. Full browser workflow tests, PostgreSQL runtime verification, and security hardening for public production remain pending.
- **Deployment:** a production-preparation runbook and liveness/readiness probes are implemented. The application is not hosted or production-verified; hosting access and PostgreSQL are not available in this environment.
