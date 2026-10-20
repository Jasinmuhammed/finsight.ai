import { PortfolioWorkspace } from "@/components/portfolio-workspace";

export default function PortfolioPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">YOUR POSITIONS</p>
          <h1>Portfolio &amp; risk</h1>
          <p className="muted">Track transactions and review historical valuations without implying live prices.</p>
        </div>
      </section>
      <PortfolioWorkspace />
    </div>
  );
}
