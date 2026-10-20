import { WatchlistsWorkspace } from "@/components/watchlists-workspace";

export default function WatchlistsPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">PERSONAL TRACKING</p>
          <h1>Watchlists &amp; alerts</h1>
          <p className="muted">
            Save instruments and review threshold alerts from fresh historical bars.
          </p>
        </div>
      </section>
      <WatchlistsWorkspace />
    </div>
  );
}
