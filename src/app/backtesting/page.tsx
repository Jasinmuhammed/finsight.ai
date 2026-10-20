import { BacktestWorkspace } from "@/components/backtest-workspace";

export default function BacktestingPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">STRATEGY LAB</p>
          <h1>Strategy backtesting</h1>
          <p className="muted">Reproducible daily-history simulations with explicit costs and execution assumptions.</p>
        </div>
      </section>
      <BacktestWorkspace />
    </div>
  );
}
