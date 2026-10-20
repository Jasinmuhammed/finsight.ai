import Link from "next/link";
import { ApiStatus } from "@/components/api-status";

const metrics = [
  { label: "Tracked instruments", value: "04", note: "Illustrative demo universe" },
  { label: "Saved screens", value: "01", note: "Starter screen" },
  { label: "Market status", value: "Demo", note: "No live market feed configured" },
];

export default function DashboardPage() {
  return (
    <div className="page-stack">
      <section className="welcome-row">
        <div>
          <p className="eyebrow">TUESDAY, OCTOBER 20</p>
          <h1>Good afternoon</h1>
          <p className="muted">Your market workspace, at a glance.</p>
        </div>
        <ApiStatus />
      </section>

      <div className="notice" role="note">
        <span className="notice-dot" />
        <div>
          <strong>Demo environment</strong>
          <p>
            Values shown are illustrative only, not live or historical exchange
            data. Connect a licensed provider before using market analysis.
          </p>
        </div>
      </div>

      <section className="metric-grid" aria-label="Workspace overview">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <p className="metric-label">{metric.label}</p>
            <p className="metric-value">{metric.value}</p>
            <p className="metric-note">{metric.note}</p>
          </article>
        ))}
      </section>

      <section className="section-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">GET STARTED</p>
            <h2>Explore your workspace</h2>
          </div>
          <Link className="text-link" href="/screener">
            Open screener <span aria-hidden="true">→</span>
          </Link>
        </div>
        <div className="action-grid">
          <Link className="action-card" href="/screener">
            <span className="action-icon" aria-hidden="true">⌕</span>
            <span>
              <strong>Screen instruments</strong>
              <small>Combine price, volume, and exchange filters.</small>
            </span>
            <span className="action-arrow" aria-hidden="true">↗</span>
          </Link>
          <div className="action-card unavailable" aria-label="Charts, coming later">
            <span className="action-icon" aria-hidden="true">⌁</span>
            <span>
              <strong>Charts &amp; analysis</strong>
              <small>Requires a configured market-data provider.</small>
            </span>
            <span className="coming-soon">Not available</span>
          </div>
        </div>
      </section>
    </div>
  );
}
