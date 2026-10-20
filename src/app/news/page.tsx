import { NewsWorkspace } from "@/components/news-workspace";

export default function NewsPage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">MARKET INTELLIGENCE</p>
          <h1>Financial news</h1>
          <p className="muted">
            Publisher-linked headlines with optional source-grounded AI summaries.
          </p>
        </div>
      </section>
      <NewsWorkspace />
    </div>
  );
}
