from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from urllib.error import HTTPError

import pandas as pd
import pytest
from curl_cffi.requests.exceptions import RequestException
from fastapi.testclient import TestClient
from yfinance.exceptions import YFException

from backend import market_data
from backend.main import app
from backend.market_data import (
    FinnhubHistoricalProvider,
    ProviderUnavailable,
    YahooFinanceHistoricalProvider,
    historical_freshness,
)


def yahoo_history(rows, index=None):
    timestamps = index
    if timestamps is None:
        timestamps = pd.date_range(
            "2024-01-02", periods=len(rows), freq="D", tz="Asia/Kolkata"
        )
    return pd.DataFrame(
        rows,
        index=timestamps,
        columns=["Open", "High", "Low", "Close", "Volume"],
    )


class FakeYahooTicker:
    def __init__(self, history):
        self.history_data = history
        self.history_calls = []

    def history(self, **kwargs):
        self.history_calls.append(kwargs)
        if isinstance(self.history_data, Exception):
            raise self.history_data
        return self.history_data


def test_yahoo_provider_explicitly_maps_supported_nse_symbols(monkeypatch):
    provider = YahooFinanceHistoricalProvider()
    tickers = {
        symbol: FakeYahooTicker(yahoo_history([[100, 105, 99, 103, 1000]]))
        for symbol in ("RELIANCE.NS", "TCS.NS", "INFY.NS")
    }
    requested = []

    def ticker(symbol):
        requested.append(symbol)
        return tickers[symbol]

    monkeypatch.setattr(market_data.yfinance, "Ticker", ticker)

    for symbol, yahoo_symbol in (
        ("RELIANCE", "RELIANCE.NS"),
        ("TCS", "TCS.NS"),
        ("INFY", "INFY.NS"),
    ):
        candles = provider.historical_daily_candles(
            symbol, "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )
        assert len(candles) == 1
        assert tickers[yahoo_symbol].history_calls[0]["interval"] == "1d"
        assert tickers[yahoo_symbol].history_calls[0]["auto_adjust"] is False

    assert requested == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    assert provider.status()["provider"] == "yahoo"
    assert provider.status()["configured"] is True
    assert "not live quotes" in provider.provenance_note.lower()


def test_yahoo_provider_search_lists_only_explicitly_mapped_symbols():
    provider = YahooFinanceHistoricalProvider()

    assert [
        (item.exchange, item.symbol)
        for item in provider.search_instruments("")
    ] == [("NSE", "RELIANCE"), ("NSE", "TCS"), ("NSE", "INFY")]
    assert [item.symbol for item in provider.search_instruments("RELI")] == [
        "RELIANCE"
    ]
    assert provider.search_instruments("UNKNOWN") == []


def test_yahoo_provider_rejects_unsupported_symbols_and_exchanges():
    provider = YahooFinanceHistoricalProvider()

    with pytest.raises(ProviderUnavailable, match="No verified Yahoo Finance"):
        provider.historical_daily_candles(
            "UNKNOWN", "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )
    with pytest.raises(ValueError, match="only validated NSE"):
        provider.historical_daily_candles(
            "RELIANCE", "BSE", date(2024, 1, 1), date(2024, 1, 3)
        )


def test_yahoo_provider_normalizes_timezone_and_inclusive_date_range(monkeypatch):
    history = yahoo_history(
        [[100, 105, 99, 103, 1000]],
        index=pd.DatetimeIndex(["2024-01-02"], tz="Asia/Kolkata"),
    )
    fake_ticker = FakeYahooTicker(history)
    monkeypatch.setattr(market_data.yfinance, "Ticker", lambda _symbol: fake_ticker)
    provider = YahooFinanceHistoricalProvider()

    candles = provider.historical_daily_candles(
        "RELIANCE", "NSE", date(2024, 1, 2), date(2024, 1, 2)
    )

    assert candles[0].timestamp == datetime(2024, 1, 1, 18, 30, tzinfo=timezone.utc)
    assert fake_ticker.history_calls[0]["start"] == "2024-01-02"
    assert fake_ticker.history_calls[0]["end"] == "2024-01-03"
    assert candles[0].volume == 1000


def test_yahoo_provider_returns_empty_for_no_history(monkeypatch):
    fake_ticker = FakeYahooTicker(yahoo_history([]))
    monkeypatch.setattr(market_data.yfinance, "Ticker", lambda _symbol: fake_ticker)

    assert YahooFinanceHistoricalProvider().historical_daily_candles(
        "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
    ) == []


@pytest.mark.parametrize(
    "rows",
    [
        [[100, 99, 101, 103, 1000]],
        [[100, 105, 99, float("nan"), 1000]],
        [[100, 105, 99, 103, -1]],
        [[100, 105, 99, 103, 1000.5]],
    ],
)
def test_yahoo_provider_rejects_invalid_ohlcv_rows(monkeypatch, rows):
    fake_ticker = FakeYahooTicker(yahoo_history(rows))
    monkeypatch.setattr(market_data.yfinance, "Ticker", lambda _symbol: fake_ticker)

    with pytest.raises(ProviderUnavailable, match="invalid daily OHLCV"):
        YahooFinanceHistoricalProvider().historical_daily_candles(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )


def test_yahoo_provider_rejects_missing_columns(monkeypatch):
    history = pd.DataFrame(
        [[100, 105, 99, 103]],
        columns=["Open", "High", "Low", "Close"],
        index=pd.DatetimeIndex(["2024-01-02"], tz="Asia/Kolkata"),
    )
    monkeypatch.setattr(
        market_data.yfinance, "Ticker", lambda _symbol: FakeYahooTicker(history)
    )

    with pytest.raises(ProviderUnavailable, match="incomplete daily OHLCV"):
        YahooFinanceHistoricalProvider().historical_daily_candles(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )


@pytest.mark.parametrize(
    ("index", "message"),
    [
        (
            pd.DatetimeIndex(["2024-01-02", "2024-01-02"], tz="Asia/Kolkata"),
            "duplicate or out-of-order",
        ),
        (
            pd.DatetimeIndex(["2024-01-03", "2024-01-02"], tz="Asia/Kolkata"),
            "duplicate or out-of-order",
        ),
        (
            pd.DatetimeIndex(["2024-01-02", "2024-01-03"]),
            "without a timezone",
        ),
    ],
)
def test_yahoo_provider_rejects_invalid_timestamps(monkeypatch, index, message):
    fake_ticker = FakeYahooTicker(
        yahoo_history(
            [[100, 105, 99, 103, 1000], [101, 106, 100, 104, 1100]],
            index=index,
        )
    )
    monkeypatch.setattr(market_data.yfinance, "Ticker", lambda _symbol: fake_ticker)

    with pytest.raises(ProviderUnavailable, match=message):
        YahooFinanceHistoricalProvider().historical_daily_candles(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )


def test_yahoo_provider_rejects_malformed_response(monkeypatch):
    monkeypatch.setattr(
        market_data.yfinance, "Ticker", lambda _symbol: FakeYahooTicker(object())
    )

    with pytest.raises(ProviderUnavailable, match="invalid daily history response"):
        YahooFinanceHistoricalProvider().historical_daily_candles(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )


@pytest.mark.parametrize(
    "error",
    [
        RequestException("network unavailable"),
        YFException("provider unavailable"),
        TimeoutError("request timed out"),
    ],
)
def test_yahoo_provider_surfaces_provider_failures_safely(monkeypatch, error):
    monkeypatch.setattr(
        market_data.yfinance,
        "Ticker",
        lambda _symbol: FakeYahooTicker(error),
    )

    with pytest.raises(ProviderUnavailable, match="service could not be reached"):
        YahooFinanceHistoricalProvider().historical_daily_candles(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )


def test_yahoo_provider_selection_is_explicit_and_does_not_affect_demo(
    monkeypatch,
):
    try:
        monkeypatch.setenv("MARKET_DATA_PROVIDER", "yahoo")
        market_data.get_market_data_provider.cache_clear()
        yahoo = market_data.get_market_data_provider()
        assert isinstance(yahoo, YahooFinanceHistoricalProvider)

        monkeypatch.setenv("MARKET_DATA_PROVIDER", "demo")
        market_data.get_market_data_provider.cache_clear()
        assert isinstance(
            market_data.get_market_data_provider(), market_data.UnconfiguredProvider
        )
    finally:
        market_data.get_market_data_provider.cache_clear()


def test_yahoo_provider_status_and_candles_api_use_selected_adapter(
    monkeypatch,
):
    fake_ticker = FakeYahooTicker(
        yahoo_history(
            [[100, 105, 99, 103, 1000]],
            index=pd.DatetimeIndex(["2024-01-02"], tz="Asia/Kolkata"),
        )
    )
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "yahoo")
    monkeypatch.setenv("ALERT_POLL_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(
        market_data.yfinance, "Ticker", lambda _symbol: fake_ticker
    )
    market_data.get_market_data_provider.cache_clear()

    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/market-data/status")
            candles = client.get(
                "/api/v1/market-data/instruments/NSE/RELIANCE/candles"
                "?start=2024-01-01&end=2024-01-03"
            )
    finally:
        market_data.get_market_data_provider.cache_clear()

    assert status.status_code == 200
    assert status.json()["provider"] == "yahoo"
    assert status.json()["status"] == "HISTORICAL"
    assert candles.status_code == 200
    assert candles.json()["source"] == "Yahoo Finance daily historical candles"
    assert candles.json()["data_status"] == "HISTORICAL"
    assert len(candles.json()["candles"]) == 1


def test_yahoo_provider_caches_historical_response(monkeypatch):
    fake_ticker = FakeYahooTicker(yahoo_history([[100, 105, 99, 103, 1000]]))
    monkeypatch.setattr(market_data.yfinance, "Ticker", lambda _symbol: fake_ticker)
    provider = YahooFinanceHistoricalProvider()
    arguments = ("RELIANCE", "NSE", date(2024, 1, 2), date(2024, 1, 2))

    first = provider.historical_daily_candles(*arguments)
    second = provider.historical_daily_candles(*arguments)

    assert first is second
    assert len(fake_ticker.history_calls) == 1


def test_finnhub_provider_requires_key_and_reports_historical_mode():
    provider = FinnhubHistoricalProvider("", "NSE:RELIANCE")
    status = provider.status()
    assert status["provider"] == "finnhub"
    assert status["status"] == "UNAVAILABLE"
    assert status["configured"] is False
    assert "FINNHUB_API_KEY" in status["message"]
    with pytest.raises(ProviderUnavailable, match="FINNHUB_API_KEY"):
        provider.historical_daily_candles("RELIANCE", "NSE")


@pytest.mark.parametrize(
    ("status_code", "expected_message"),
    [
        (401, "Finnhub rejected the configured credentials or endpoint access."),
        (403, "Finnhub rejected the configured credentials or endpoint access."),
        (429, "Finnhub rate limit reached; retry after the provider limit resets."),
        (500, "Finnhub historical data request failed (HTTP 500)."),
    ],
)
def test_finnhub_http_error_logs_only_status_code(
    monkeypatch, caplog, status_code, expected_message
):
    secret = "sensitive-test-token"
    response_body = b"sensitive-test-response-body"
    provider = FinnhubHistoricalProvider(secret)

    def raise_http_error(*_args, **_kwargs):
        raise HTTPError(
            f"https://provider.invalid/path?token={secret}&query=sensitive-query",
            status_code,
            "sensitive-test-reason",
            {"Authorization": f"Bearer {secret}"},
            BytesIO(response_body),
        )

    monkeypatch.setattr(market_data, "urlopen", raise_http_error)

    with caplog.at_level("WARNING", logger=market_data.__name__):
        with pytest.raises(ProviderUnavailable) as error:
            provider._request_json(
                "stock/candle",
                {"symbol": "NSE:RELIANCE", "sensitive-param": secret},
            )

    assert str(error.value) == expected_message
    assert len(caplog.records) == 1
    assert caplog.records[0].message == (
        f"Finnhub request failed with upstream HTTP status {status_code}."
    )
    assert caplog.records[0].args == (status_code,)
    assert secret not in caplog.text
    assert "sensitive-query" not in caplog.text
    assert "sensitive-test-reason" not in caplog.text
    assert response_body.decode() not in caplog.text


def test_finnhub_provider_validates_configured_screen_universe():
    with pytest.raises(ValueError, match="EXCHANGE:SYMBOL"):
        FinnhubHistoricalProvider("secret", "RELIANCE")
    with pytest.raises(ValueError, match="at most"):
        FinnhubHistoricalProvider(
            "secret",
            ",".join(f"NSE:TEST{index}" for index in range(1001)),
        )


def test_finnhub_history_maps_daily_ohlcv_and_caches_provider_response(monkeypatch):
    provider = FinnhubHistoricalProvider("server-token", "NSE:RELIANCE")
    requested: list[dict] = []

    def response(endpoint, params):
        requested.append({"endpoint": endpoint, **params})
        return {
            "s": "ok",
            "t": [1704153600, 1704240000],
            "o": [100, 103],
            "h": [105, 108],
            "l": [99, 102],
            "c": [103, 107],
            "v": [1000, 1500],
        }

    monkeypatch.setattr(provider, "_request_json", response)
    first = provider.historical_daily_candles(
        "reliance", "NSE", date(2024, 1, 1), date(2024, 1, 3)
    )
    second = provider.historical_daily_candles(
        "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
    )
    assert first == second
    assert len(requested) == 1
    assert requested[0]["endpoint"] == "stock/candle"
    assert requested[0]["symbol"] == "NSE:RELIANCE"
    assert requested[0]["resolution"] == "D"
    assert first[0].timestamp == datetime(2024, 1, 2, tzinfo=timezone.utc)
    assert first[0].close == 103
    assert first[0].volume == 1000
    assert "not live quotes" in provider.provenance_note.lower()


def test_finnhub_provider_returns_no_data_and_rejects_malformed_responses(monkeypatch):
    provider = FinnhubHistoricalProvider("secret")
    monkeypatch.setattr(provider, "_request_json", lambda *_args: {"s": "no_data"})
    assert (
        provider.historical_daily_candles(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 2)
        )
        == []
    )

    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *_args: {
            "s": "ok",
            "t": [1704153600, 1704240000],
            "o": [100],
            "h": [105, 108],
            "l": [99, 102],
            "c": [103, 107],
            "v": [1000, 1500],
        },
    )
    with pytest.raises(ProviderUnavailable, match="mismatched"):
        provider.historical_daily_candles(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )


def test_finnhub_rejects_out_of_order_daily_candles(monkeypatch):
    provider = FinnhubHistoricalProvider("secret")
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *_args: {
            "s": "ok",
            "t": [1704240000, 1704153600],
            "o": [103, 100],
            "h": [108, 105],
            "l": [102, 99],
            "c": [107, 103],
            "v": [1500, 1000],
        },
    )

    with pytest.raises(ProviderUnavailable, match="chronological order"):
        provider.historical_daily_candles(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 3)
        )


def test_finnhub_provider_filters_symbol_search_to_supported_exchanges(monkeypatch):
    provider = FinnhubHistoricalProvider("secret", "NSE:RELIANCE")
    requests = []

    def search(*args):
        requests.append(args)
        return {
            "result": [
                {"symbol": "NSE:RELIANCE", "description": "Reliance Industries"},
                {"symbol": "NASDAQ:AAPL", "description": "Apple Inc"},
                {"symbol": "BSE:500325", "description": "Reliance Industries"},
                {"symbol": "NSE:RELIANCE", "description": "Reliance Industries"},
                {"description": "Missing symbol"},
            ]
        }

    monkeypatch.setattr(
        provider,
        "_request_json",
        search,
    )
    results = provider.search_instruments("Reliance")
    assert provider.search_instruments("Reliance") == results
    assert len(requests) == 1
    assert [(item.exchange, item.symbol) for item in results] == [
        ("BSE", "500325"),
        ("NSE", "RELIANCE"),
    ]


def test_finnhub_search_uses_configured_exchange_for_unprefixed_symbol(monkeypatch):
    provider = FinnhubHistoricalProvider("secret", "NSE:RELIANCE")
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *_args: {
            "count": 1,
            "result": [
                {
                    "description": "Reliance Industries",
                    "displaySymbol": "RELIANCE",
                    "symbol": "RELIANCE",
                    "type": "Common Stock",
                }
            ],
        },
    )

    results = provider.search_instruments("RELIANCE")

    assert [(item.exchange, item.symbol, item.name) for item in results] == [
        ("NSE", "RELIANCE", "Reliance Industries")
    ]


def test_finnhub_search_discards_ambiguous_unprefixed_symbols(monkeypatch):
    provider = FinnhubHistoricalProvider(
        "secret", "NSE:RELIANCE,BSE:RELIANCE"
    )
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *_args: {
            "result": [
                {"symbol": "RELIANCE", "description": "Reliance Industries"},
                {"symbol": "NASDAQ:AAPL", "description": "Apple Inc"},
            ]
        },
    )

    assert provider.search_instruments("Industries") == []


def test_finnhub_search_empty_result_is_empty(monkeypatch):
    provider = FinnhubHistoricalProvider("secret", "NSE:RELIANCE")
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *_args: {"count": 0, "result": []},
    )

    assert provider.search_instruments("not-a-match") == []


def test_finnhub_search_includes_matching_configured_universe_on_empty_provider_result(
    monkeypatch,
):
    provider = FinnhubHistoricalProvider(
        "secret", "NSE:RELIANCE,BSE:500325,NSE:TCS"
    )
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *_args: {"count": 0, "result": []},
    )

    results = provider.search_instruments("reli")

    assert [(item.exchange, item.symbol) for item in results] == [
        ("NSE", "RELIANCE")
    ]


def test_finnhub_search_result_preserves_provider_symbol_for_candles(monkeypatch):
    provider = FinnhubHistoricalProvider("secret", "NSE:RELIANCE")
    requests = []

    def request(endpoint, params):
        requests.append((endpoint, params))
        if endpoint == "search":
            return {
                "result": [
                    {"symbol": "RELIANCE", "description": "Reliance Industries"}
                ]
            }
        return {
            "s": "ok",
            "t": [1704153600],
            "o": [100],
            "h": [105],
            "l": [99],
            "c": [103],
            "v": [1000],
        }

    monkeypatch.setattr(provider, "_request_json", request)
    instrument = provider.search_instruments("RELIANCE")[0]

    provider.historical_daily_candles(
        instrument.symbol,
        instrument.exchange,
        date(2024, 1, 1),
        date(2024, 1, 3),
    )

    assert requests[0][0] == "search"
    assert requests[1][0] == "stock/candle"
    assert requests[1][1]["symbol"] == "RELIANCE"


def test_finnhub_search_conflicting_provider_symbols_are_not_guessed(monkeypatch):
    provider = FinnhubHistoricalProvider("secret", "NSE:RELIANCE")
    requests = []

    def request(endpoint, params):
        requests.append((endpoint, params))
        if endpoint == "search":
            return {
                "result": [
                    {"symbol": "RELIANCE", "description": "Reliance Industries"},
                    {"symbol": "NSE:RELIANCE", "description": "Reliance Industries"},
                ]
            }
        return {"s": "no_data"}

    monkeypatch.setattr(provider, "_request_json", request)
    instrument = provider.search_instruments("RELIANCE")[0]

    with pytest.raises(ProviderUnavailable, match="conflicting symbols"):
        provider.historical_daily_candles(
            instrument.symbol,
            instrument.exchange,
            date(2024, 1, 1),
            date(2024, 1, 3),
        )

    assert [endpoint for endpoint, _params in requests] == ["search"]


def test_freshness_classifies_historical_timestamps_without_calling_them_live():
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    assert historical_freshness(today) == "RECENT_HISTORY"
    assert historical_freshness(
        datetime(2000, 1, 1, tzinfo=timezone.utc)
    ) == "STALE_HISTORY"
    assert historical_freshness(None) == "UNKNOWN"


def test_market_data_provider_selects_finnhub_with_explicit_missing_key_status(
    monkeypatch,
):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "finnhub")
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setenv("FINNHUB_SYMBOLS", "NSE:RELIANCE")
    market_data.get_market_data_provider.cache_clear()
    provider = market_data.get_market_data_provider()
    assert provider.name == "finnhub"
    assert provider.status()["configured"] is False
    assert provider.status()["universe_configured"] is True


def test_finnhub_selection_does_not_fall_back_to_configured_csv(tmp_path, monkeypatch):
    (tmp_path / "NSE_RELIANCE.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-02,10,12,9,11,100\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "finnhub")
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setenv("FINNHUB_SYMBOLS", "NSE:RELIANCE")
    monkeypatch.setenv("MARKET_DATA_CSV_DIR", str(tmp_path))
    monkeypatch.setenv("ALERT_POLL_INTERVAL_SECONDS", "0")
    market_data.get_market_data_provider.cache_clear()

    with TestClient(app) as client:
        status = client.get("/api/v1/market-data/status")
        candles = client.get(
            "/api/v1/market-data/instruments/NSE/RELIANCE/candles"
        )

    assert status.status_code == 200
    assert status.json()["provider"] == "finnhub"
    assert status.json()["status"] == "UNAVAILABLE"
    assert candles.status_code == 503
    assert "FINNHUB_API_KEY" in candles.json()["detail"]


def test_candles_endpoint_reports_finnhub_source_and_historical_freshness(
    monkeypatch,
):
    latest_completed_date = datetime.now(market_data.MARKET_TIMEZONE).date() - timedelta(days=1)
    latest_completed_epoch = int(
        datetime.combine(
            latest_completed_date, datetime.min.time(), tzinfo=timezone.utc
        ).timestamp()
    )
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "finnhub")
    monkeypatch.setenv("FINNHUB_API_KEY", "server-token")
    monkeypatch.setenv("FINNHUB_SYMBOLS", "NSE:RELIANCE")
    monkeypatch.setenv("ALERT_POLL_INTERVAL_SECONDS", "0")
    market_data.get_market_data_provider.cache_clear()
    monkeypatch.setattr(
        FinnhubHistoricalProvider,
        "_request_json",
        lambda *_args: {
            "s": "ok",
            "t": [latest_completed_epoch],
            "o": [100],
            "h": [105],
            "l": [99],
            "c": [103],
            "v": [1000],
        },
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/market-data/instruments/NSE/RELIANCE/candles"
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_status"] == "HISTORICAL"
    assert payload["source"] == "Finnhub daily historical candles"
    assert payload["freshness_status"] == "RECENT_HISTORY"
    assert "not live quotes" in payload["provenance_note"].lower()


def test_empty_finnhub_history_has_explicit_unknown_freshness(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "finnhub")
    monkeypatch.setenv("FINNHUB_API_KEY", "server-token")
    monkeypatch.setenv("FINNHUB_SYMBOLS", "NSE:RELIANCE")
    monkeypatch.setenv("ALERT_POLL_INTERVAL_SECONDS", "0")
    market_data.get_market_data_provider.cache_clear()
    monkeypatch.setattr(
        FinnhubHistoricalProvider,
        "_request_json",
        lambda *_args: {"s": "no_data"},
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/market-data/instruments/NSE/RELIANCE/candles"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candles"] == []
    assert payload["freshness_status"] == "UNKNOWN"
    assert payload["data_as_of"] is None
    assert payload["data_status"] == "HISTORICAL"


def test_market_data_api_rejects_invalid_symbol_and_date_range(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "finnhub")
    monkeypatch.setenv("FINNHUB_API_KEY", "server-token")
    monkeypatch.setenv("FINNHUB_SYMBOLS", "NSE:RELIANCE")
    market_data.get_market_data_provider.cache_clear()

    with TestClient(app) as client:
        invalid_symbol = client.get(
            "/api/v1/market-data/instruments/NSE/INVALID%20SYMBOL/candles"
        )
        invalid_dates = client.get(
            "/api/v1/market-data/instruments/NSE/RELIANCE/candles"
            "?start=2024-02-01&end=2024-01-01"
        )

    assert invalid_symbol.status_code == 422
    assert invalid_dates.status_code == 422


def test_market_data_api_surfaces_provider_failures(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "finnhub")
    monkeypatch.setenv("FINNHUB_API_KEY", "server-token")
    monkeypatch.setenv("FINNHUB_SYMBOLS", "")
    monkeypatch.setenv("ALERT_POLL_INTERVAL_SECONDS", "0")
    market_data.get_market_data_provider.cache_clear()
    monkeypatch.setattr(
        FinnhubHistoricalProvider,
        "_request_json",
        lambda *_args: (_ for _ in ()).throw(
            ProviderUnavailable("Finnhub rejected the configured credentials or endpoint access.")
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/market-data/instruments/NSE/RELIANCE/candles"
        )

    assert response.status_code == 503
    assert "rejected the configured credentials" in response.json()["detail"]


def test_historical_screener_uses_finnhub_universe_source_and_freshness(
    monkeypatch,
):
    today_market_date = datetime.now(market_data.MARKET_TIMEZONE).date()
    latest_completed_date = today_market_date - timedelta(days=1)
    timestamp = int(
        datetime.combine(
            latest_completed_date, datetime.min.time(), tzinfo=timezone.utc
        ).timestamp()
    )
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "finnhub")
    monkeypatch.setenv("FINNHUB_API_KEY", "server-token")
    monkeypatch.setenv("FINNHUB_SYMBOLS", "NSE:RELIANCE")
    monkeypatch.setenv("ALERT_POLL_INTERVAL_SECONDS", "0")
    market_data.get_market_data_provider.cache_clear()
    monkeypatch.setattr(
        FinnhubHistoricalProvider,
        "_request_json",
        lambda *_args: {
            "s": "ok",
            "t": [timestamp],
            "o": [100],
            "h": [105],
            "l": [99],
            "c": [103],
            "v": [1000],
        },
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/market-data/screener", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "Finnhub daily historical candles"
    assert payload["freshness_status"] == "RECENT_HISTORY"
    assert payload["results"][0]["symbol"] == "RELIANCE"
    assert payload["results"][0]["freshness_status"] == "RECENT_HISTORY"
