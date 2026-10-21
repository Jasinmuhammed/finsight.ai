"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type NewsArticle = {
  source: string;
  source_id: string;
  headline: string;
  summary: string;
  url: string;
  published_at: string;
  related_symbols: string[];
};

type NewsResponse = {
  data_status: "NEWS";
  source: string;
  articles: NewsArticle[];
  ai_status: "NOT_REQUESTED" | "NO_ARTICLES" | "UNAVAILABLE" | "AVAILABLE";
  ai_summary: string | null;
};

export function NewsWorkspace() {
  const [symbol, setSymbol] = useState("");
  const [news, setNews] = useState<NewsResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadNews = useCallback(async (query: string, summarize = false) => {
    setError("");
    setLoading(true);
    const params = new URLSearchParams({ limit: "20" });
    if (query.trim()) params.set("symbol", query.trim());
    if (summarize) params.set("summarize_ai", "true");
    try {
      const response = await fetch(`${apiBase}/news?${params.toString()}`);
      const payload = (await response.json()) as NewsResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          "detail" in payload && payload.detail
            ? payload.detail
            : `News request failed (${response.status}).`,
        );
      }
      setNews(payload as NewsResponse);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load news.");
      setNews(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadNews("");
  }, [loadNews]);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadNews(symbol);
  }

  return (
    <div className="page-stack">
      <section className="section-card">
        <div className="section-heading">
          <div>
            <h2>Publisher headlines</h2>
            <p className="muted">
              Finnhub news requires a server-side FINNHUB_API_KEY. Symbol search uses
              the provider&apos;s own ticker format.
            </p>
          </div>
          <span className="demo-tag">EXTERNAL SOURCES</span>
        </div>
        <form className="news-search-form" onSubmit={search}>
          <label className="field">
            Provider ticker (optional)
            <input
              autoComplete="off"
              maxLength={32}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="e.g. AAPL or NSE:RELIANCE"
              value={symbol}
            />
          </label>
          <button className="primary-button" disabled={loading} type="submit">
            {loading ? "Loading..." : "Load headlines"}
          </button>
        </form>
        {error && (
          <div className="notice news-notice" role="alert">
            <span className="notice-dot" />
            <div>
              <strong>News unavailable</strong>
              <p>{error}</p>
            </div>
          </div>
        )}
      </section>

      {news && (
        <>
          <section className="section-card">
            <div className="section-heading">
              <div>
                <h2>{news.articles.length} source articles</h2>
                <p className="muted">
                  Source: {news.source}. Publisher dates and links are preserved.
                </p>
              </div>
              <button
                className="secondary-button"
                disabled={loading || news.articles.length === 0}
                onClick={() => void loadNews(symbol, true)}
                type="button"
              >
                Summarize with AI
              </button>
            </div>
            {news.ai_status === "AVAILABLE" && news.ai_summary && (
              <div className="ai-summary" aria-live="polite">
                <strong>AI summary · cites numbered source articles</strong>
                <p>{news.ai_summary}</p>
              </div>
            )}
            {news.ai_status === "UNAVAILABLE" && (
              <div className="notice news-notice" role="status">
                <span className="notice-dot" />
                <div>
                  <strong>AI summary unavailable</strong>
                  <p>
                    Gemini did not provide a summary for these articles. The
                    source headlines remain available; no generated text is shown.
                  </p>
                </div>
              </div>
            )}
            {news.ai_status === "NO_ARTICLES" && (
              <p className="muted">There are no source articles to summarize.</p>
            )}
          </section>
          <section className="news-list" aria-label="Financial news articles">
            {news.articles.map((article, index) => (
              <article className="section-card news-article" key={article.source_id}>
                <div className="news-article-meta">
                  <span>{index + 1} · {article.source}</span>
                  <span className="news-time">
                    {Number.isFinite(Date.parse(article.published_at)) ? (
                      <time dateTime={article.published_at}>
                        {new Date(article.published_at).toLocaleString()}
                      </time>
                    ) : (
                      <span>Publication time unavailable</span>
                    )}
                    {Number.isFinite(Date.parse(article.published_at)) &&
                      Date.now() - Date.parse(article.published_at) > 7 * 86_400_000 && (
                        <strong className="news-stale-tag">Older than 7 days</strong>
                      )}
                  </span>
                </div>
                <h2>
                  <a href={article.url} rel="noreferrer" target="_blank">
                    {article.headline}
                  </a>
                </h2>
                {article.summary ? (
                  <p className="news-excerpt">{article.summary}</p>
                ) : (
                  <p className="muted">The publisher did not provide an excerpt.</p>
                )}
                <a className="text-link" href={article.url} rel="noreferrer" target="_blank">
                  Read at {article.source} ↗
                </a>
              </article>
            ))}
            {news.articles.length === 0 && (
              <div className="section-card">
                <p className="muted">The provider returned no articles for this query.</p>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
