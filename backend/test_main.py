import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend import auth
from backend.database import Base, get_db
from backend.main import app
from backend.market_data import get_market_data_provider

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as database:
            yield database

    app.dependency_overrides[get_db] = override_get_db
    auth.attempts.clear()
    get_market_data_provider.cache_clear()
    yield
    app.dependency_overrides.clear()
    get_market_data_provider.cache_clear()
    engine.dispose()


def register(email: str = "investor@example.com") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Correct horse battery 42"},
    )
    assert response.status_code == 201
    return response.json()


def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_check_verifies_database():
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_reports_database_failure():
    class UnavailableDatabase:
        def execute(self, _statement):
            raise SQLAlchemyError("private connection detail")

    def unavailable_database():
        yield UnavailableDatabase()

    app.dependency_overrides[get_db] = unavailable_database
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Database readiness check failed."


def test_screener_applies_and_filters():
    response = client.post(
        "/api/v1/screener",
        json={"min_price": 1000, "min_change_percent": 1, "combine": "AND"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_status"] == "DEMO"
    assert payload["count"] == 2
    assert {item["symbol"] for item in payload["results"]} == {"DEMO1", "DEMO3"}


def test_screener_supports_or_filters():
    response = client.post(
        "/api/v1/screener",
        json={"max_price": 500, "min_change_percent": 2, "combine": "OR"},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert {item["symbol"] for item in response.json()["results"]} == {"DEMO3", "DEMO4"}


def test_screener_rejects_invalid_ranges():
    response = client.post(
        "/api/v1/screener", json={"min_price": 100, "max_price": 50}
    )
    assert response.status_code == 422


def test_unknown_instrument_returns_not_found():
    response = client.get("/api/v1/instruments/UNKNOWN")
    assert response.status_code == 404


def test_registration_hashes_password_and_sets_secure_cookie():
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "Investor@Example.com", "password": "Correct horse battery 42"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "investor@example.com"
    assert "password" not in response.json()
    cookie = response.headers["set-cookie"]
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    assert "finsight_session=" in cookie
    assert client.get("/api/v1/auth/me").json()["email"] == "investor@example.com"


def test_duplicate_registration_and_weak_password_are_rejected():
    register()
    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": "INVESTOR@example.com", "password": "Correct horse battery 42"},
    )
    weak = client.post(
        "/api/v1/auth/register",
        json={"email": "second@example.com", "password": "short"},
    )
    assert duplicate.status_code == 409
    assert weak.status_code == 422


def test_login_and_logout_revoke_session():
    register()
    client.cookies.clear()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "investor@example.com", "password": "Correct horse battery 42"},
    )
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_password_has_generic_error():
    register()
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "investor@example.com", "password": "Wrong password phrase"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_saved_screens_are_isolated_by_user():
    register("first@example.com")
    first_screen = client.post(
        "/api/v1/screens",
        json={"name": "Value setup", "filters": {"min_price": 100}},
    )
    assert first_screen.status_code == 201
    first_id = first_screen.json()["id"]

    client.post(
        "/api/v1/auth/logout",
    )
    register("second@example.com")
    assert client.get("/api/v1/screens").json() == []
    delete_other_users_screen = client.delete(f"/api/v1/screens/{first_id}")
    assert delete_other_users_screen.status_code == 404


def test_saved_screen_requires_authenticated_user():
    response = client.get("/api/v1/screens")
    assert response.status_code == 401


def test_historical_provider_is_explicitly_unavailable_without_configuration(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "demo")
    get_market_data_provider.cache_clear()
    status_response = client.get("/api/v1/market-data/status")
    candle_response = client.get(
        "/api/v1/market-data/instruments/NSE/RELIANCE/candles"
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "UNAVAILABLE"
    assert candle_response.status_code == 503


def test_user_csv_provider_returns_validated_historical_data(tmp_path, monkeypatch):
    (tmp_path / "NSE_SAMPLE.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-02,10,12,9,11,1500\n"
        "2024-01-03,11,13,10,12,1800\n"
        "2024-01-04,12,16,11,15,3600\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "csv")
    monkeypatch.setenv("MARKET_DATA_CSV_DIR", str(tmp_path))
    get_market_data_provider.cache_clear()

    search = client.get("/api/v1/market-data/instruments/search?query=sample")
    response = client.get(
        "/api/v1/market-data/instruments/NSE/SAMPLE/candles"
    )
    assert search.status_code == 200
    assert search.json()[0]["symbol"] == "SAMPLE"
    assert response.status_code == 200
    data = response.json()
    assert data["data_status"] == "HISTORICAL"
    assert data["source"] == "User-supplied CSV"
    assert len(data["candles"]) == 3
    assert data["candles"][0]["timestamp"].endswith("Z")
    assert "not independently verified" in data["provenance_note"]
    indicators = client.get(
        "/api/v1/market-data/instruments/NSE/SAMPLE/indicators"
        "?sma_period=2&ema_period=2&rsi_period=2"
    )
    patterns = client.get(
        "/api/v1/market-data/instruments/NSE/SAMPLE/patterns"
        "?lookback=2&volume_multiplier=1.5"
    )
    assert indicators.status_code == 200
    assert indicators.json()["data_status"] == "HISTORICAL"
    assert indicators.json()["indicators"]["sma"] == [None, 11.5, 13.5]
    assert patterns.status_code == 200
    assert len(patterns.json()["patterns"]) == 1
    assert patterns.json()["patterns"][0]["prior_range_high"] == 13


def test_user_csv_rejects_invalid_ohlc_and_duplicate_timestamps(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "csv")
    monkeypatch.setenv("MARKET_DATA_CSV_DIR", str(tmp_path))
    get_market_data_provider.cache_clear()
    path = tmp_path / "NSE_BAD.csv"
    path.write_text(
        "Date,Open,High,Low,Close,Volume\n2024-01-02,10,9,8,10,100\n",
        encoding="utf-8",
    )
    invalid_ohlc = client.get(
        "/api/v1/market-data/instruments/NSE/BAD/candles"
    )
    assert invalid_ohlc.status_code == 422

    path.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-02,10,12,8,11,100\n"
        "2024-01-02T15:00:00+05:30,10,12,8,11,100\n",
        encoding="utf-8",
    )
    duplicate = client.get("/api/v1/market-data/instruments/NSE/BAD/candles")
    assert duplicate.status_code == 422


def test_user_csv_rejects_untrusted_symbol_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "csv")
    monkeypatch.setenv("MARKET_DATA_CSV_DIR", str(tmp_path))
    get_market_data_provider.cache_clear()
    response = client.get(
        "/api/v1/market-data/instruments/NSE/%2E%2E%2Fsecret/candles"
    )
    assert response.status_code in {404, 422}


def test_backtest_endpoint_requires_auth_and_persists_historical_result(
    tmp_path, monkeypatch
):
    (tmp_path / "NSE_SAMPLE.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-01,9,10,8,9,1000\n"
        "2024-01-02,9,11,8.5,10,1000\n"
        "2024-01-03,10,12,9,12,1000\n"
        "2024-01-04,12,14,11,12,1000\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "csv")
    monkeypatch.setenv("MARKET_DATA_CSV_DIR", str(tmp_path))
    get_market_data_provider.cache_clear()
    request = {
        "symbol": "SAMPLE",
        "exchange": "NSE",
        "strategy": {
            "entry_rule": "range_breakout",
            "breakout_lookback": 2,
            "initial_capital": 10000,
            "position_size_percent": 50,
            "brokerage_bps": 0,
            "slippage_bps": 0,
            "take_profit_percent": 10,
        },
    }
    assert client.post("/api/v1/backtests/run", json=request).status_code == 401
    register()
    response = client.post("/api/v1/backtests/run", json=request)
    assert response.status_code == 200
    assert response.json()["result"]["data_status"] == "HISTORICAL"
    assert response.json()["result"]["trade_count"] == 1
    assert response.json()["result"]["trades"][0]["entry_at"].startswith("2024-01-04")


def test_advanced_screener_combines_indicators_and_breakout_conditions(
    tmp_path, monkeypatch
):
    alpha_rows = ["Date,Open,High,Low,Close,Volume"]
    beta_rows = ["Date,Open,High,Low,Close,Volume"]
    for index in range(25):
        day = index + 1
        alpha_close = 130 if index == 24 else 100 + index
        alpha_rows.append(
            f"2024-01-{day:02d},{alpha_close - 1},{alpha_close + 1},"
            f"{alpha_close - 2},{alpha_close},{3000 if index == 24 else 1000}"
        )
        beta_close = 200 - index
        beta_rows.append(
            f"2024-01-{day:02d},{beta_close + 1},{beta_close + 2},"
            f"{beta_close - 1},{beta_close},1000"
        )
    (tmp_path / "NSE_ALPHA.csv").write_text("\n".join(alpha_rows), encoding="utf-8")
    (tmp_path / "BSE_BETA.csv").write_text("\n".join(beta_rows), encoding="utf-8")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "csv")
    monkeypatch.setenv("MARKET_DATA_CSV_DIR", str(tmp_path))
    get_market_data_provider.cache_clear()

    response = client.post(
        "/api/v1/market-data/screener",
        json={
            "min_relative_volume": 2,
            "min_rsi": 60,
            "price_above_sma": 20,
            "breakout_lookback": 20,
            "combine": "AND",
            "sort_by": "relative_volume",
            "sort_order": "desc",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_status"] == "HISTORICAL"
    assert payload["count"] == 1
    assert payload["results"][0]["symbol"] == "ALPHA"
    assert payload["results"][0]["relative_volume"] == 3
    assert len(payload["results"][0]["matched_conditions"]) == 4


def test_advanced_screener_or_filter_and_pagination(tmp_path, monkeypatch):
    (tmp_path / "NSE_ALPHA.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-01,10,11,9,10,100\n"
        "2024-01-02,11,12,10,11,100\n",
        encoding="utf-8",
    )
    (tmp_path / "BSE_BETA.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-01,20,21,19,20,100\n"
        "2024-01-02,19,20,18,19,100\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "csv")
    monkeypatch.setenv("MARKET_DATA_CSV_DIR", str(tmp_path))
    get_market_data_provider.cache_clear()
    response = client.post(
        "/api/v1/market-data/screener",
        json={
            "min_price": 10,
            "max_change_percent": -1,
            "combine": "OR",
            "sort_by": "symbol",
            "limit": 1,
            "offset": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["symbol"] == "BETA"


def test_advanced_screener_rejects_invalid_ranges():
    response = client.post(
        "/api/v1/market-data/screener",
        json={"min_rsi": 80, "max_rsi": 20},
    )
    assert response.status_code == 422


def test_portfolio_accounting_and_user_isolation():
    register("owner@example.com")
    created = client.post(
        "/api/v1/portfolios",
        json={"name": "Long term", "initial_cash": 1000},
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]
    transaction_url = f"/api/v1/portfolios/{portfolio_id}/transactions"
    buy = client.post(
        transaction_url,
        json={
            "symbol": "SAMPLE",
            "exchange": "NSE",
            "side": "BUY",
            "quantity": 10,
            "price": 20,
            "fees": 0,
            "transacted_at": "2024-01-01T09:00:00Z",
        },
    )
    assert buy.status_code == 201
    invalid_sell = client.post(
        transaction_url,
        json={
            "symbol": "SAMPLE",
            "exchange": "NSE",
            "side": "SELL",
            "quantity": 11,
            "price": 30,
            "fees": 0,
            "transacted_at": "2024-01-02T09:00:00Z",
        },
    )
    assert invalid_sell.status_code == 422
    sell = client.post(
        transaction_url,
        json={
            "symbol": "SAMPLE",
            "exchange": "NSE",
            "side": "SELL",
            "quantity": 5,
            "price": 30,
            "fees": 1,
            "transacted_at": "2024-01-02T09:00:00Z",
        },
    )
    assert sell.status_code == 201
    overview = client.get(f"/api/v1/portfolios/{portfolio_id}/overview")
    assert overview.status_code == 200
    assert overview.json()["cash_balance"] == 949
    assert overview.json()["realized_pnl"] == 49
    assert overview.json()["holdings"][0]["quantity"] == 5
    assert overview.json()["valuation_status"] == "UNAVAILABLE"
    assert overview.json()["total_value"] is None
    assert client.get(transaction_url).json()[0]["side"] == "BUY"

    client.post("/api/v1/auth/logout")
    register("other@example.com")
    assert client.get("/api/v1/portfolios").json() == []
    assert client.get(f"/api/v1/portfolios/{portfolio_id}/overview").status_code == 404
    assert client.get(transaction_url).status_code == 404


def test_portfolio_transactions_can_be_updated_and_deleted():
    register()
    portfolio = client.post(
        "/api/v1/portfolios", json={"name": "Editable", "initial_cash": 500}
    ).json()
    base = f"/api/v1/portfolios/{portfolio['id']}/transactions"
    buy = client.post(
        base,
        json={
            "symbol": "TEST",
            "exchange": "BSE",
            "side": "BUY",
            "quantity": 10,
            "price": 20,
            "transacted_at": "2024-01-01T00:00:00Z",
        },
    ).json()
    update = client.put(
        f"{base}/{buy['id']}",
        json={
            "symbol": "TEST",
            "exchange": "BSE",
            "side": "BUY",
            "quantity": 5,
            "price": 20,
            "transacted_at": "2024-01-01T00:00:00Z",
        },
    )
    assert update.status_code == 200
    assert update.json()["quantity"] == 5
    assert client.delete(f"{base}/{buy['id']}").status_code == 204
    assert client.get(f"/api/v1/portfolios/{portfolio['id']}/overview").json()["cash_balance"] == 500


def test_state_changing_portfolio_endpoint_rejects_untrusted_origin():
    response = client.post(
        "/api/v1/portfolios",
        headers={"Origin": "https://attacker.example"},
        json={"name": "Not allowed", "initial_cash": 10},
    )
    assert response.status_code == 403


def test_cors_allows_authenticated_transaction_updates_from_configured_frontend():
    response = client.options(
        "/api/v1/portfolios/example/transactions/example",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_cors_allows_watchlist_alert_patch_from_configured_frontend():
    response = client.options(
        "/api/v1/alerts/example",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_watchlist_crud_is_owner_scoped_and_rejects_duplicates():
    register("watch-owner@example.com")
    created = client.post("/api/v1/watchlists", json={"name": "Core holdings"})
    assert created.status_code == 201
    watchlist_id = created.json()["id"]
    assert client.post(
        "/api/v1/watchlists", json={"name": "Core holdings"}
    ).status_code == 409

    item = client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        json={"symbol": "sample", "exchange": "NSE"},
    )
    assert item.status_code == 201
    assert item.json()["symbol"] == "SAMPLE"
    assert client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        json={"symbol": "SAMPLE", "exchange": "NSE"},
    ).status_code == 409
    assert client.get("/api/v1/watchlists").json()[0]["instruments"][0]["id"] == item.json()["id"]

    client.post("/api/v1/auth/logout")
    register("watch-other@example.com")
    assert client.get("/api/v1/watchlists").json() == []
    assert client.delete(f"/api/v1/watchlists/{watchlist_id}").status_code == 404


def test_alert_lifecycle_is_owner_scoped_and_provider_unavailability_is_clear():
    assert client.post(
        "/api/v1/alerts",
        json={"symbol": "SAMPLE", "exchange": "NSE", "operator": "ABOVE", "target_price": 10},
    ).status_code == 401
    register("alert-owner@example.com")
    created = client.post(
        "/api/v1/alerts",
        json={
            "symbol": "sample",
            "exchange": "NSE",
            "operator": "ABOVE",
            "target_price": 100,
            "cooldown_seconds": 3600,
        },
    )
    assert created.status_code == 201
    alert_id = created.json()["id"]
    assert created.json()["symbol"] == "SAMPLE"
    assert client.get("/api/v1/alerts").json()[0]["id"] == alert_id
    assert client.post("/api/v1/alerts/poll").status_code == 503
    disabled = client.patch(f"/api/v1/alerts/{alert_id}", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    client.post("/api/v1/auth/logout")
    register("alert-other@example.com")
    assert client.get("/api/v1/alerts").json() == []
    assert client.patch(
        f"/api/v1/alerts/{alert_id}", json={"enabled": True}
    ).status_code == 404
