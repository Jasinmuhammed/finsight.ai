import { HistoricalChart } from "@/components/historical-chart";

export default function ChartsPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">PRICE ACTION</p>
          <h1>Charts &amp; patterns</h1>
          <p className="muted">Explore imported daily candles with transparent indicator rules.</p>
        </div>
      </section>
      <HistoricalChart />
    </div>
  );
}
