# Deployment preparation

This runbook documents a production deployment shape; FinSight AI has not been deployed or verified on a hosting provider. PostgreSQL, provider credentials, backup/monitoring services, and deployment access must be supplied before production readiness can be claimed.

## Required services

- A PostgreSQL database reachable from the API runtime.
- A Python 3.12+ API runtime and a Node.js 20.9+ frontend runtime.
- HTTPS endpoints for both services.
- A frontend origin configured in the API CORS and request-origin allowlists.
- An operator-managed secret store for provider keys and database credentials.

SQLite is suitable for local development only. The application supports PostgreSQL through `DATABASE_URL`, but PostgreSQL runtime behavior has not been verified in this environment.

## API configuration

Set these variables in the API service, not in browser-visible frontend configuration:

- `DATABASE_URL`: PostgreSQL SQLAlchemy URL. Require TLS using the syntax supported by your provider/driver.
- `SESSION_COOKIE_SECURE=true`.
- `AUTH_ALLOWED_ORIGINS`: comma-separated exact HTTPS frontend origins; do not use wildcard origins with cookies.
- `ALERT_POLL_INTERVAL_SECONDS`: set to `300` or `0` to disable scheduled alert polling. The scheduler is in-process; run exactly one API process while it is enabled.
- `MARKET_DATA_PROVIDER` and `MARKET_DATA_CSV_DIR`: optional user-supplied historical CSV configuration. CSV data remains historical and its rights/provenance are the operator's responsibility.
- `FINNHUB_API_KEY`: optional server-side financial-news access; verify account limits, attribution, and permitted use.
- `GEMINI_API_KEY` and optional `GEMINI_MODEL`: optional server-side article summaries. Do not add these to `NEXT_PUBLIC_*` variables.

Do not commit `.env`, credentials, user datasets, or database dumps. Rotate any credentials that may have been exposed.

## Release sequence

1. Provision the PostgreSQL database, TLS, backups, monitoring, and secret storage.
2. Configure API and frontend service variables and exact allowed origins.
3. Take a database backup and run the release migration once:

   ```powershell
   python -m alembic upgrade head
   ```

4. Start the API service with a single process if scheduled alerts are enabled:

   ```powershell
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

5. Configure `NEXT_PUBLIC_API_BASE_URL` as a build-time frontend variable, pointing to the public API URL ending in `/api/v1`. Build and start the frontend service:

   ```powershell
   npm run build
   npm run start -- --hostname 0.0.0.0 --port 3000
   ```

   Adapt ports and process supervision to the hosting provider. Do not use `--reload` in production.

6. Run the smoke checks below from the deployment network, then verify logs, database backups, and provider terms before accepting real user data.

## Smoke checks

```powershell
curl.exe -f https://API_HOST/api/v1/health
curl.exe -f https://API_HOST/api/v1/health/ready
curl.exe -f https://FRONTEND_HOST/news
curl.exe -f https://FRONTEND_HOST/watchlists
```

Expected API responses are `200` for liveness and for readiness when the database is reachable. The news API should return an explicit unavailable response when `FINNHUB_API_KEY` is absent; it must not substitute sample headlines. Complete an account registration/login and owner-isolation check in a controlled staging environment before enabling public access.

## Not yet verified

- PostgreSQL connectivity, concurrent transactions, and migration behavior on the target service.
- Host-specific build/start commands, TLS termination, cookie behavior, CORS, and assigned-port handling.
- Real Finnhub/Gemini credentials, account limits, legal/attribution requirements, and provider response behavior.
- Backup restoration, monitoring, incident response, rate limiting across replicas, and multi-worker alert scheduling.
- Public deployment security review and browser end-to-end coverage.
