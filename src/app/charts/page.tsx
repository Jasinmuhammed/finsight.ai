import { HistoricalChart } from "@/components/historical-chart";

export default function ChartsPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">CHART WORKSPACE</p>
          <h1>Chart analysis</h1>
          <p className="muted">Explore historical candles, technical overlays, and rule-based pattern markers.</p>
        </div>
      </section>
      <HistoricalChart mode="chart" />
    </div>
  );
}
