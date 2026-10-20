"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type WatchlistItem = {
  id: string;
  symbol: string;
  exchange: "NSE" | "BSE";
};

type Watchlist = {
  id: string;
  name: string;
  instruments: WatchlistItem[];
};

type AlertRule = {
  id: string;
  symbol: string;
  exchange: "NSE" | "BSE";
  operator: "ABOVE" | "BELOW";
  target_price: number;
  enabled: boolean;
};

type AlertEvent = {
  id: string;
  alert_id: string;
  symbol: string;
  exchange: "NSE" | "BSE";
  message: string;
  triggered_value: number;
  data_status: "HISTORICAL" | "UNAVAILABLE";
  data_as_of: string | null;
  created_at: string;
  read_at: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!response.ok) {
    const result = (await response.json()) as { detail?: string };
    throw new Error(
      result.detail ?? `Request failed (${response.status}).`,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function WatchlistsWorkspace() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [alerts, setAlerts] = useState<AlertRule[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [selectedWatchlist, setSelectedWatchlist] = useState("");
  const [watchlistName, setWatchlistName] = useState("");
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState<"NSE" | "BSE">("NSE");
  const [alertSymbol, setAlertSymbol] = useState("");
  const [alertExchange, setAlertExchange] = useState<"NSE" | "BSE">("NSE");
  const [operator, setOperator] = useState<"ABOVE" | "BELOW">("ABOVE");
  const [target, setTarget] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [listResult, alertResult, eventResult] = await Promise.all([
        request<Watchlist[]>("/watchlists"),
        request<AlertRule[]>("/alerts"),
        request<AlertEvent[]>("/alerts/events?limit=100"),
      ]);
      setWatchlists(listResult);
      setAlerts(alertResult);
      setEvents(eventResult);
      setSelectedWatchlist((current) =>
        listResult.some((item) => item.id === current)
          ? current
          : listResult[0]?.id ?? "",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load saved data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  async function perform<T>(
    action: () => Promise<T>,
    success: string | ((result: T) => string),
  ) {
    setError("");
    setNotice("");
    try {
      const result = await action();
      await loadWorkspace();
      setNotice(typeof success === "function" ? success(result) : success);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The action could not be completed.");
    }
  }

  function createWatchlist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void perform(async () => {
      const created = await request<Watchlist>("/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: watchlistName }),
      });
      setWatchlistName("");
      setSelectedWatchlist(created.id);
    }, "Watchlist created.");
  }

  function addInstrument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWatchlist) return;
    void perform(async () => {
      await request(`/watchlists/${selectedWatchlist}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, exchange }),
      });
      setSymbol("");
    }, "Instrument added.");
  }

  function createAlert(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void perform(async () => {
      await request("/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: alertSymbol,
          exchange: alertExchange,
          operator,
          target_price: Number(target),
          cooldown_seconds: 3600,
        }),
      });
      setAlertSymbol("");
      setTarget("");
    }, "Historical threshold alert created.");
  }

  function pollNow() {
    void perform(
      () =>
        request<{ created_events: number; skipped_alerts: number; message: string }>("/alerts/poll", {
          method: "POST",
        }),
      (result) => `${result.message} New events: ${result.created_events}.`,
    );
  }

  const activeWatchlist = watchlists.find((item) => item.id === selectedWatchlist);

  return (
    <div className="page-stack">
      <div className="notice">
        <span className="notice-dot" />
        <div>
          <strong>Historical data only</strong>
          <p>
            Alerts evaluate newly timestamped daily CSV bars no more than four days
            old. They are not live-price notifications. Configure a CSV provider
            and the API polling interval for scheduled evaluation.
          </p>
        </div>
      </div>

      {(error || notice) && (
        <div className={error ? "portfolio-error" : "portfolio-success"} role={error ? "alert" : "status"}>
          {error || notice}
          {error.toLowerCase().includes("not authenticated") && (
            <> <Link className="text-link" href="/login">Sign in</Link></>
          )}
        </div>
      )}

      <div className="watchlist-grid">
        <section className="section-card">
          <div className="section-heading">
            <div>
              <h2>Your watchlists</h2>
              <p className="muted">Private to your account.</p>
            </div>
          </div>
          <form className="watchlist-create-form" onSubmit={createWatchlist}>
            <label className="field">
              New list name
              <input
                maxLength={80}
                onChange={(event) => setWatchlistName(event.target.value)}
                required
                value={watchlistName}
              />
            </label>
            <button className="primary-button" disabled={loading} type="submit">
              Create list
            </button>
          </form>
          <div className="watchlist-list">
            {watchlists.map((watchlist) => (
              <button
                className={`watchlist-choice ${selectedWatchlist === watchlist.id ? "selected" : ""}`}
                key={watchlist.id}
                onClick={() => setSelectedWatchlist(watchlist.id)}
                type="button"
              >
                <span>{watchlist.name}</span>
                <small>{watchlist.instruments.length} instruments</small>
              </button>
            ))}
            {!watchlists.length && <p className="muted">Create a watchlist to get started.</p>}
          </div>
        </section>

        <section className="section-card">
          <div className="section-heading">
            <div>
              <h2>{activeWatchlist?.name ?? "Watchlist instruments"}</h2>
              <p className="muted">Symbols are saved without implying price freshness.</p>
            </div>
            {activeWatchlist && (
              <button
                className="secondary-button"
                onClick={() => void perform(
                  () => request(`/watchlists/${activeWatchlist.id}`, { method: "DELETE" }),
                  "Watchlist deleted.",
                )}
                type="button"
              >
                Delete list
              </button>
            )}
          </div>
          <form className="instrument-add-form" onSubmit={addInstrument}>
            <label className="field">
              Symbol
              <input
                autoComplete="off"
                maxLength={32}
                onChange={(event) => setSymbol(event.target.value)}
                required
                value={symbol}
              />
            </label>
            <label className="field">
              Exchange
              <select onChange={(event) => setExchange(event.target.value as "NSE" | "BSE")} value={exchange}>
                <option value="NSE">NSE</option>
                <option value="BSE">BSE</option>
              </select>
            </label>
            <button className="primary-button" disabled={loading || !selectedWatchlist} type="submit">
              Add symbol
            </button>
          </form>
          <div className="watchlist-instruments">
            {activeWatchlist?.instruments.map((item) => (
              <div className="watchlist-instrument" key={item.id}>
                <strong>{item.symbol}</strong>
                <span>{item.exchange}</span>
                <button
                  aria-label={`Remove ${item.symbol} from ${activeWatchlist.name}`}
                  className="secondary-button"
                  onClick={() => void perform(
                    () => request(`/watchlists/${activeWatchlist.id}/items/${item.id}`, { method: "DELETE" }),
                    "Instrument removed.",
                  )}
                  type="button"
                >
                  Remove
                </button>
              </div>
            ))}
            {activeWatchlist && !activeWatchlist.instruments.length && (
              <p className="muted">This watchlist is empty.</p>
            )}
          </div>
        </section>
      </div>

      <section className="section-card">
        <div className="section-heading">
          <div>
            <h2>Price threshold alerts</h2>
            <p className="muted">Conditions are checked against fresh historical daily closes.</p>
          </div>
          <button className="secondary-button" disabled={loading} onClick={pollNow} type="button">
            Poll historical bars
          </button>
        </div>
        <form className="alert-create-form" onSubmit={createAlert}>
          <label className="field">
            Symbol
            <input
              autoComplete="off"
              maxLength={32}
              onChange={(event) => setAlertSymbol(event.target.value)}
              required
              value={alertSymbol}
            />
          </label>
          <label className="field">
            Exchange
            <select onChange={(event) => setAlertExchange(event.target.value as "NSE" | "BSE")} value={alertExchange}>
              <option value="NSE">NSE</option>
              <option value="BSE">BSE</option>
            </select>
          </label>
          <label className="field">
            Condition
            <select onChange={(event) => setOperator(event.target.value as "ABOVE" | "BELOW")} value={operator}>
              <option value="ABOVE">Close at or above</option>
              <option value="BELOW">Close at or below</option>
            </select>
          </label>
          <label className="field">
            Target price (INR)
            <input
              inputMode="decimal"
              min="0.01"
              onChange={(event) => setTarget(event.target.value)}
              required
              step="any"
              type="number"
              value={target}
            />
          </label>
          <button className="primary-button" disabled={loading} type="submit">
            Save alert
          </button>
        </form>
        <div className="alert-list">
          {alerts.map((alert) => (
            <div className="alert-row" key={alert.id}>
              <div>
                <strong>{alert.exchange}:{alert.symbol}</strong>
                <p className="muted">
                  Close {alert.operator.toLowerCase()} INR {alert.target_price.toLocaleString()}
                </p>
              </div>
              <span className={`alert-state ${alert.enabled ? "enabled" : ""}`}>
                {alert.enabled ? "Enabled" : "Paused"}
              </span>
              <button
                className="secondary-button"
                onClick={() => void perform(
                  () => request(`/alerts/${alert.id}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ enabled: !alert.enabled }),
                  }),
                  alert.enabled ? "Alert paused." : "Alert enabled.",
                )}
                type="button"
              >
                {alert.enabled ? "Pause" : "Enable"}
              </button>
              <button
                className="secondary-button"
                onClick={() => void perform(
                  () => request(`/alerts/${alert.id}`, { method: "DELETE" }),
                  "Alert deleted.",
                )}
                type="button"
              >
                Delete
              </button>
            </div>
          ))}
          {!alerts.length && <p className="muted">No alerts have been configured.</p>}
        </div>
      </section>

      <section className="section-card">
        <div className="section-heading">
          <div>
            <h2>Alert history</h2>
            <p className="muted">Each event includes the historical bar timestamp that triggered it.</p>
          </div>
        </div>
        <div className="alert-list">
          {events.map((event) => (
            <div className={`alert-row ${event.read_at ? "read" : ""}`} key={event.id}>
              <div>
                <strong>{event.message}</strong>
                <p className="muted">
                  {event.data_status === "HISTORICAL" && event.data_as_of
                    ? `Historical bar: ${new Date(event.data_as_of).toLocaleString()}`
                    : "Source timestamp unavailable"}
                </p>
              </div>
              <span className="demo-tag">{event.data_status}</span>
              {!event.read_at && (
                <button
                  className="secondary-button"
                  onClick={() => void perform(
                    () => request(`/alerts/events/${event.id}/read`, { method: "PUT" }),
                    "Alert event marked read.",
                  )}
                  type="button"
                >
                  Mark read
                </button>
              )}
            </div>
          ))}
          {!events.length && <p className="muted">No alert events yet.</p>}
        </div>
      </section>
    </div>
  );
}
