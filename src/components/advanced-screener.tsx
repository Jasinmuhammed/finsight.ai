"use client";

import { FormEvent, useEffect, useState } from "react";

type ScreenerFilters = {
  exchange: string | null;
  min_price: number | null;
  min_rsi: number | null;
  max_rsi: number | null;
  min_relative_volume: number | null;
  price_above_sma: number | null;
  breakout_lookback: number | null;
  combine: "AND" | "OR";
  sort_by: string;
  sort_order: "asc" | "desc";
  limit: number;
  offset: number;
};

type ScreenerResult = {
  symbol: string;
  name: string;
  exchange: string;
  last_price: number;
  change_percent: number | null;
  volume: number;
  relative_volume: number | null;
  rsi: number | null;
  sma: number | null;
  ema: number | null;
  matched_conditions: string[];
  data_as_of: string;
  freshness_status: "RECENT_HISTORY" | "STALE_HISTORY" | "UNKNOWN";
};

type ScreenerPayload = {
  results: ScreenerResult[];
  count: number;
  limit: number;
  offset: number;
  data_status: "HISTORICAL";
  source: string;
  data_as_of: string | null;
  freshness_status:
    | "RECENT_HISTORY"
    | "STALE_HISTORY"
    | "MIXED_HISTORY"
    | "UNKNOWN";
};

type SavedScreen = {
  id: string;
  name: string;
  filters: ScreenerFilters;
};

type ProviderStatus = {
  provider: string;
  status: string;
  configured: boolean;
  universe_configured?: boolean;
  message: string;
};

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatValue(value: number | null, digits = 2) {
  return value === null ? "—" : value.toFixed(digits);
}

export function AdvancedScreener() {
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [minPrice, setMinPrice] = useState("");
  const [minRsi, setMinRsi] = useState("");
  const [maxRsi, setMaxRsi] = useState("");
  const [minRelativeVolume, setMinRelativeVolume] = useState("");
  const [smaPeriod, setSmaPeriod] = useState("");
  const [breakoutLookback, setBreakoutLookback] = useState("");
  const [combine, setCombine] = useState<"AND" | "OR">("AND");
  const [sortBy, setSortBy] = useState("relative_volume");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [exchange, setExchange] = useState("");
  const [payload, setPayload] = useState<ScreenerPayload | null>(null);
  const [screens, setScreens] = useState<SavedScreen[]>([]);
  const [screenName, setScreenName] = useState("");
  const [error, setError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);

  function currentFilters(offset = 0): ScreenerFilters {
    return {
      exchange: exchange || null,
      min_price: numberOrNull(minPrice),
      min_rsi: numberOrNull(minRsi),
      max_rsi: numberOrNull(maxRsi),
      min_relative_volume: numberOrNull(minRelativeVolume),
      price_above_sma: numberOrNull(smaPeriod),
      breakout_lookback: numberOrNull(breakoutLookback),
      combine,
      sort_by: sortBy,
      sort_order: sortOrder,
      limit: 25,
      offset,
    };
  }

  async function loadFilters(filters: ScreenerFilters) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/market-data/screener`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(filters),
      });
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail || `Screener request failed (${response.status}).`);
      }
      setPayload((await response.json()) as ScreenerPayload);
      setPage(Math.floor(filters.offset / filters.limit));
    } catch (requestError) {
      setPayload(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load historical screener results.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBase}/market-data/status`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Provider status failed (${response.status}).`);
        const data = (await response.json()) as ProviderStatus;
        setProvider(data);
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name !== "AbortError") {
          setProvider({
            provider: "unavailable",
            status: "UNAVAILABLE",
            configured: false,
            message: requestError.message,
          });
        }
      });
    fetch(`${apiBase}/screens`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.ok) setScreens((await response.json()) as SavedScreen[]);
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name !== "AbortError") {
          setSavedMessage("Sign in to access your saved screens.");
        }
      });
    return () => controller.abort();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await loadFilters(currentFilters());
  }

  async function saveCurrentScreen() {
    setSavedMessage("");
    if (!screenName.trim()) {
      setSavedMessage("Enter a name for this screen.");
      return;
    }
    try {
      const response = await fetch(`${apiBase}/screens`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: screenName.trim(),
          filters: currentFilters(),
        }),
      });
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail || `Could not save screen (${response.status}).`);
      }
      const saved = (await response.json()) as SavedScreen;
      setScreens((previous) => [saved, ...previous.filter((item) => item.id !== saved.id)]);
      setScreenName("");
      setSavedMessage("Screen saved to your account.");
    } catch (saveError) {
      setSavedMessage(
        saveError instanceof Error ? saveError.message : "Could not save this screen.",
      );
    }
  }

  async function runSavedScreen(screen: SavedScreen) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/screens/${screen.id}/results`, {
        credentials: "include",
      });
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail || `Could not run saved screen (${response.status}).`);
      }
      setPayload((await response.json()) as ScreenerPayload);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Could not run saved screen.");
    } finally {
      setLoading(false);
    }
  }

  async function deleteSavedScreen(screen: SavedScreen) {
    try {
      const response = await fetch(`${apiBase}/screens/${screen.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        setSavedMessage(body.detail || `Could not delete screen (${response.status}).`);
        return;
      }
      setScreens((previous) => previous.filter((item) => item.id !== screen.id));
    } catch (deleteError) {
      setSavedMessage(
        deleteError instanceof Error ? deleteError.message : "Could not delete this screen.",
      );
    }
  }

  return (
    <section className="section-card advanced-screener">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">HISTORICAL DATA</p>
          <h2>Advanced screener</h2>
        </div>
        <span className={`provider-tag ${provider?.configured ? "configured" : ""}`}>
          {provider?.status ?? "CHECKING"}
        </span>
      </div>
      <p className="data-provenance">
        Scans daily historical candles from the configured provider; these are historical bars,
        never live quotes. Source and latest-bar age are shown with results.
      </p>
      {provider && !provider.configured && (
        <div className="provider-warning" role="status">
          {provider.message}{" "}
          {provider.provider === "finnhub" ? (
            <>Configure <code>FINNHUB_API_KEY</code>, then restart the API.</>
          ) : (
            <>Configure <code>MARKET_DATA_PROVIDER=csv</code> and{" "}
            <code>MARKET_DATA_CSV_DIR</code>, then restart the API.</>
          )}
        </div>
      )}
      {provider?.provider === "finnhub" &&
        provider.configured &&
        !provider.universe_configured && (
          <div className="provider-warning" role="status">
            Configure a comma-separated <code>FINNHUB_SYMBOLS</code> universe
            (for example <code>NSE:RELIANCE,BSE:500325</code>) and restart the API
            to enable whole-universe screening.
          </div>
      )}
      <form className="advanced-filter-form" onSubmit={submit}>
        <label className="field">
          <span>Exchange</span>
          <select onChange={(event) => setExchange(event.target.value)} value={exchange}>
            <option value="">Any</option>
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
          </select>
        </label>
        <label className="field">
          <span>Minimum price (₹)</span>
          <input min="0" onChange={(event) => setMinPrice(event.target.value)} type="number" value={minPrice} />
        </label>
        <label className="field">
          <span>Minimum RSI</span>
          <input min="0" max="100" onChange={(event) => setMinRsi(event.target.value)} type="number" value={minRsi} />
        </label>
        <label className="field">
          <span>Maximum RSI</span>
          <input min="0" max="100" onChange={(event) => setMaxRsi(event.target.value)} type="number" value={maxRsi} />
        </label>
        <label className="field">
          <span>Minimum relative volume</span>
          <input min="0" step="0.1" onChange={(event) => setMinRelativeVolume(event.target.value)} type="number" value={minRelativeVolume} />
        </label>
        <label className="field">
          <span>Price above SMA</span>
          <input min="2" max="252" onChange={(event) => setSmaPeriod(event.target.value)} placeholder="Off" type="number" value={smaPeriod} />
        </label>
        <label className="field">
          <span>Breakout lookback</span>
          <input min="2" max="252" onChange={(event) => setBreakoutLookback(event.target.value)} placeholder="Off" type="number" value={breakoutLookback} />
        </label>
        <label className="field">
          <span>Combine filters</span>
          <select onChange={(event) => setCombine(event.target.value as "AND" | "OR")} value={combine}>
            <option value="AND">Match all (AND)</option>
            <option value="OR">Match any (OR)</option>
          </select>
        </label>
        <label className="field">
          <span>Sort by</span>
          <select onChange={(event) => setSortBy(event.target.value)} value={sortBy}>
            <option value="relative_volume">Relative volume</option>
            <option value="price">Price</option>
            <option value="change_percent">Price change</option>
            <option value="volume">Volume</option>
            <option value="rsi">RSI</option>
            <option value="symbol">Symbol</option>
          </select>
        </label>
        <label className="field">
          <span>Sort direction</span>
          <select onChange={(event) => setSortOrder(event.target.value as "asc" | "desc")} value={sortOrder}>
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </select>
        </label>
        <button
          className="primary-button"
          disabled={
            loading ||
            !provider?.configured ||
            (provider.provider === "finnhub" && !provider.universe_configured)
          }
          type="submit"
        >
          {loading ? "Screening…" : "Run historical screen"}
        </button>
      </form>

      <div className="save-screen-row">
        <label className="field">
          <span>Save current filter set</span>
          <input
            maxLength={80}
            onChange={(event) => setScreenName(event.target.value)}
            placeholder="e.g. High-volume breakouts"
            value={screenName}
          />
        </label>
        <button className="secondary-button" onClick={() => void saveCurrentScreen()} type="button">
          Save screen
        </button>
        {savedMessage && <span className="saved-message" role="status">{savedMessage}</span>}
      </div>

      {screens.length > 0 && (
        <div className="saved-screen-list">
          <strong>Saved screens</strong>
          {screens.map((screen) => (
            <div className="saved-screen-item" key={screen.id}>
              <span>{screen.name}</span>
              <button onClick={() => void runSavedScreen(screen)} type="button">Run</button>
              <button onClick={() => void deleteSavedScreen(screen)} type="button">Delete</button>
            </div>
          ))}
        </div>
      )}

      {error && <div className="error-state inline-error" role="alert">{error}</div>}
      {payload && (
        <div className="historical-results">
          <div className="section-heading compact">
            <h3>{payload.count} historical matches</h3>
            <span className="updated-label">
              Latest bar {payload.data_as_of ? new Date(payload.data_as_of).toLocaleDateString() : "unavailable"}
            </span>
          </div>
          {payload.results.length ? (
            <>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th><th>Exchange</th><th>Close (₹)</th><th>Change</th>
                      <th>Volume</th><th>Rel. vol.</th><th>RSI</th><th>Freshness</th><th>Matched rules</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payload.results.map((item) => (
                      <tr key={`${item.exchange}-${item.symbol}`}>
                        <td><strong>{item.symbol}</strong><small className="table-subtitle">{item.name}</small></td>
                        <td>{item.exchange}</td>
                        <td>{item.last_price.toFixed(2)}</td>
                        <td>{formatValue(item.change_percent)}%</td>
                        <td>{item.volume.toLocaleString("en-IN")}</td>
                        <td>{formatValue(item.relative_volume)}×</td>
                        <td>{formatValue(item.rsi)}</td>
                        <td>
                          {item.freshness_status === "RECENT_HISTORY"
                            ? "Recent history"
                            : item.freshness_status === "STALE_HISTORY"
                              ? "Stale history"
                              : "Unknown"}
                        </td>
                        <td>{item.matched_conditions.length ? item.matched_conditions.join(", ") : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="pagination-row">
                <span>{payload.source}</span>
                <div>
                  <button
                    className="secondary-button"
                    disabled={payload.offset === 0 || loading}
                    onClick={() => void loadFilters(currentFilters(Math.max(0, payload.offset - payload.limit)))}
                    type="button"
                  >Previous</button>
                  <span> Page {page + 1} </span>
                  <button
                    className="secondary-button"
                    disabled={payload.offset + payload.limit >= payload.count || loading}
                    onClick={() => void loadFilters(currentFilters(payload.offset + payload.limit))}
                    type="button"
                  >Next</button>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state"><strong>No matching historical instruments</strong><p>Review your filter conditions and try again.</p></div>
          )}
        </div>
      )}
    </section>
  );
}
