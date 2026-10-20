"use client";

import { FormEvent, useEffect, useState } from "react";

type Instrument = {
  symbol: string;
  name: string;
  exchange: "NSE" | "BSE";
  currency: "INR";
  price: number;
  change_percent: number;
  volume: number;
};

type ScreenerResponse = {
  results: Instrument[];
  count: number;
  data_as_of: string;
  data_status: "DEMO";
  source: string;
};

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatVolume(value: number) {
  return new Intl.NumberFormat("en-IN").format(value);
}

export function Screener() {
  const [payload, setPayload] = useState<ScreenerResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [minimumPrice, setMinimumPrice] = useState("");
  const [exchange, setExchange] = useState("");

  async function loadResults(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/screener`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          min_price: minimumPrice ? Number(minimumPrice) : null,
          exchange: exchange || null,
          combine: "AND",
        }),
      });
      if (!response.ok) {
        throw new Error(`Screener request failed (${response.status}).`);
      }
      const data = (await response.json()) as ScreenerResponse;
      setPayload(data);
    } catch (requestError) {
      setPayload(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load screener results.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadResults();
  }, []);

  return (
    <>
      <section className="section-card filter-card">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">FILTER BUILDER</p>
            <h2>Define your criteria</h2>
          </div>
          <span className="demo-tag">DEMO DATA</span>
        </div>
        <form className="filter-form" onSubmit={loadResults}>
          <label className="field">
            <span>Minimum price (₹)</span>
            <input
              inputMode="decimal"
              min="0"
              onChange={(event) => setMinimumPrice(event.target.value)}
              placeholder="Any"
              type="number"
              value={minimumPrice}
            />
          </label>
          <label className="field">
            <span>Exchange</span>
            <select onChange={(event) => setExchange(event.target.value)} value={exchange}>
              <option value="">All exchanges</option>
              <option value="NSE">NSE</option>
              <option value="BSE">BSE</option>
            </select>
          </label>
          <button className="primary-button" disabled={loading} type="submit">
            {loading ? "Screening…" : "Run screen"}
          </button>
        </form>
      </section>

      <section className="section-card results-card">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">RESULTS</p>
            <h2>{payload ? `${payload.count} instruments found` : "Screen results"}</h2>
          </div>
          {payload && (
            <span className="updated-label">
              Response time {new Date(payload.data_as_of).toLocaleTimeString()}
            </span>
          )}
        </div>

        {loading ? (
          <div className="loading-state" aria-live="polite">
            <span className="spinner" /> Loading screener results…
          </div>
        ) : error ? (
          <div className="error-state" role="alert">
            <strong>Could not load results</strong>
            <p>{error} Check that the FinSight API is running, then try again.</p>
            <button className="secondary-button" onClick={() => void loadResults()} type="button">
              Try again
            </button>
          </div>
        ) : payload?.results.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Instrument</th>
                  <th>Exchange</th>
                  <th>Last price</th>
                  <th>Change</th>
                  <th className="numeric">Volume</th>
                </tr>
              </thead>
              <tbody>
                {payload.results.map((instrument) => (
                  <tr key={instrument.symbol}>
                    <td>
                      <strong>{instrument.symbol}</strong>
                      <small className="table-subtitle">{instrument.name}</small>
                    </td>
                    <td><span className="exchange-chip">{instrument.exchange}</span></td>
                    <td>{formatMoney(instrument.price)}</td>
                    <td className={instrument.change_percent >= 0 ? "positive" : "negative"}>
                      {instrument.change_percent > 0 ? "+" : ""}
                      {instrument.change_percent.toFixed(2)}%
                    </td>
                    <td className="numeric">{formatVolume(instrument.volume)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="table-footnote">
              {payload.source}. No values on this page represent actual exchange prices.
            </p>
          </div>
        ) : (
          <div className="empty-state">
            <span aria-hidden="true">⌕</span>
            <strong>No matching instruments</strong>
            <p>Adjust your filters and run the screen again.</p>
          </div>
        )}
      </section>
    </>
  );
}
