from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend import main as main_module
from backend import news
from backend.main import app


client = TestClient(app)


def make_article() -> dict:
    return {
        "source": "Publisher",
        "source_id": "article-1",
        "headline": "A source headline",
        "summary": "A source excerpt.",
        "url": "https://publisher.example/article-1",
        "published_at": datetime(2025, 1, 2, tzinfo=timezone.utc),
        "related_symbols": ["SAMPLE"],
    }


def test_news_reports_missing_provider_key(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    response = client.get("/api/v1/news")
    assert response.status_code == 503
    assert "FINNHUB_API_KEY" in response.json()["detail"]


def test_news_returns_publisher_sources_and_honest_ai_fallback(monkeypatch):
    monkeypatch.setattr(main_module, "fetch_financial_news", lambda **_kwargs: [make_article()])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    response = client.get("/api/v1/news?summarize_ai=true")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "Finnhub"
    assert payload["articles"][0]["url"] == "https://publisher.example/article-1"
    assert payload["ai_status"] == "UNAVAILABLE"
    assert payload["ai_summary"] is None


def test_news_ai_summary_returns_source_linked_result(monkeypatch):
    monkeypatch.setattr(main_module, "fetch_financial_news", lambda **_kwargs: [make_article()])
    monkeypatch.setattr(
        main_module, "summarize_news_with_gemini", lambda _articles: "Grounded point [1]."
    )

    response = client.get("/api/v1/news?summarize_ai=true")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_status"] == "AVAILABLE"
    assert payload["ai_summary"] == "Grounded point [1]."
    assert payload["articles"][0]["url"] == "https://publisher.example/article-1"


def test_news_rejects_invalid_provider_symbol(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    response = client.get("/api/v1/news?symbol=%3Cscript%3E")
    assert response.status_code == 422


def test_finnhub_adapter_filters_invalid_articles_and_keeps_only_source_links(
    monkeypatch,
):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(
        news,
        "_request_json",
        lambda _url, **_kwargs: [
            {
                "id": 1,
                "headline": "Valid source",
                "url": "https://publisher.example/valid",
                "datetime": 1735776000,
                "source": "Publisher",
            },
            {
                "id": 2,
                "headline": "Invalid link",
                "url": "javascript:alert(1)",
                "datetime": 1735776000,
            },
        ],
    )
    articles = news.fetch_financial_news()
    assert len(articles) == 1
    assert articles[0]["url"] == "https://publisher.example/valid"
    assert articles[0]["published_at"].tzinfo == timezone.utc


def test_gemini_adapter_keeps_key_server_side_and_passes_source_links(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "server-only-key")
    captured: dict = {}

    def fake_request(url, *, headers, body):
        captured.update(url=url, headers=headers, body=body)
        return {
            "candidates": [
                {"content": {"parts": [{"text": "A summary [1]."}]}}
            ]
        }

    monkeypatch.setattr(news, "_request_json", fake_request)
    summary = news.summarize_news_with_gemini([make_article()])
    assert summary == "A summary [1]."
    assert "server-only-key" not in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "server-only-key"
    prompt = captured["body"]["contents"][0]["parts"][0]["text"]
    assert "https://publisher.example/article-1" in prompt
