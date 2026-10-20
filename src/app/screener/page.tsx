import { Screener } from "@/components/screener";
import { AdvancedScreener } from "@/components/advanced-screener";

export default function ScreenerPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">DISCOVER</p>
          <h1>Stock screener</h1>
          <p className="muted">
            Explore the development dataset with explainable filters.
          </p>
        </div>
      </section>
      <Screener />
      <AdvancedScreener />
    </div>
  );
}
