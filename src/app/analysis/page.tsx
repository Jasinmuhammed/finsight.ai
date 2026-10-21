import { HistoricalChart } from "@/components/historical-chart";

export default function StockAnalysisPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">HISTORICAL ANALYSIS</p>
          <h1>Stock analysis</h1>
          <p className="muted">
            Review provider-backed daily history, technical indicators, and descriptive risk metrics.
          </p>
        </div>
      </section>
      <HistoricalChart mode="analysis" />
    </div>
  );
}
