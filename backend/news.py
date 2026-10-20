from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_RESPONSE_BYTES = 2_000_000
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._:-]{1,32}$")


class NewsServiceUnavailable(Exception):
    pass


class NewsServiceError(Exception):
    pass


def _request_json(
    url: str, *, headers: dict[str, str] | None = None, body: dict | None = None
) -> dict | list:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url,
        data=data,
        headers={"Accept": "application/json", **(headers or {})},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise NewsServiceError(
            f"News provider returned HTTP {error.code}."
        ) from error
    except (URLError, TimeoutError) as error:
        raise NewsServiceError("News provider could not be reached.") from error
    if len(payload) > MAX_RESPONSE_BYTES:
        raise NewsServiceError("News provider response exceeded the size limit.")
    try:
        result = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise NewsServiceError("News provider returned invalid JSON.") from error
    if not isinstance(result, (dict, list)):
        raise NewsServiceError("News provider returned an unexpected response.")
    return result


def fetch_financial_news(
    *, limit: int = 20, symbol: str | None = None
) -> list[dict]:
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not api_key:
        raise NewsServiceUnavailable(
            "Financial news is unavailable. Configure FINNHUB_API_KEY to enable the Finnhub provider."
        )
    params: dict[str, str] = {"token": api_key}
    if symbol:
        normalized_symbol = symbol.strip().upper()
        if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
            raise ValueError("Symbol contains unsupported characters.")
        today = datetime.now(timezone.utc).date()
        params.update(
            {
                "symbol": normalized_symbol,
                "from": (today - timedelta(days=7)).isoformat(),
                "to": today.isoformat(),
            }
        )
        endpoint = f"https://finnhub.io/api/v1/company-news?{urlencode(params)}"
    else:
        params.update({"category": "general"})
        endpoint = f"{FINNHUB_NEWS_URL}?{urlencode(params)}"
    payload = _request_json(endpoint)
    if not isinstance(payload, list):
        raise NewsServiceError("Finnhub returned an unexpected news response.")

    articles = []
    for item in payload[:limit]:
        if not isinstance(item, dict):
            continue
        headline = item.get("headline")
        url = item.get("url")
        published_timestamp = item.get("datetime")
        if (
            not isinstance(headline, str)
            or not headline.strip()
            or not isinstance(url, str)
            or not url.startswith(("https://", "http://"))
            or not isinstance(published_timestamp, (int, float))
            or not math.isfinite(published_timestamp)
        ):
            continue
        try:
            published_at = datetime.fromtimestamp(published_timestamp, timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        articles.append(
            {
                "source": str(item.get("source") or "Finnhub")[:128],
                "source_id": str(item.get("id") or url)[:255],
                "headline": headline.strip()[:512],
                "summary": str(item.get("summary") or "")[:4000],
                "url": url,
                "published_at": published_at,
                "related_symbols": [
                    value.strip()
                    for value in str(item.get("related") or "").split(",")
                    if value.strip()
                ][:20],
            }
        )
    return articles


def summarize_news_with_gemini(articles: list[dict]) -> str | None:
    if not articles:
        return None
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", model):
        raise NewsServiceError("GEMINI_MODEL contains unsupported characters.")
    source_material = [
        {
            "headline": article["headline"],
            "excerpt": article["summary"][:1200],
            "source": article["source"],
            "url": article["url"],
        }
        for article in articles[:10]
    ]
    prompt = (
        "Summarize only the facts present in these source headlines and excerpts. "
        "Do not add outside knowledge or infer causes. Cite each key point using "
        "the source number in brackets, such as [1]. If evidence is insufficient, say so.\n"
        + json.dumps(source_material, ensure_ascii=True)
    )
    endpoint = (
        f"{GEMINI_URL}/{model}:generateContent"
    )
    response = _request_json(
        endpoint,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        body={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 500},
        },
    )
    candidates = response.get("candidates") if isinstance(response, dict) else None
    if not isinstance(candidates, list) or not candidates:
        raise NewsServiceError("Gemini returned no summary.")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    first_part = parts[0] if isinstance(parts, list) and parts else None
    text = first_part.get("text") if isinstance(first_part, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise NewsServiceError("Gemini returned an empty summary.")
    return text.strip()[:5000]
