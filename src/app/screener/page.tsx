import { AdvancedScreener } from "@/components/advanced-screener";

export default function ScreenerPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">DISCOVER</p>
          <h1>Stock screener</h1>
          <p className="muted">
            Filter supported instruments using validated daily historical data.
          </p>
        </div>
      </section>
      <AdvancedScreener />
    </div>
  );
}
