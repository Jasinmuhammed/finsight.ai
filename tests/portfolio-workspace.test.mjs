import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const workspace = readFileSync(
  new URL("../src/components/portfolio-workspace.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(new URL("../backend/main.py", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("portfolio shows fee-inclusive invested cost and actual historical price provenance", () => {
  assert.match(api, /total_invested_capital=total_invested_capital/);
  assert.match(api, /invested_amount=float\(state\.cost_basis\)/);
  assert.match(workspace, /Invested in open holdings/);
  assert.match(workspace, /Weighted average incl\. buy charges/);
  assert.match(workspace, /Historical price/);
  assert.match(workspace, /holding\.price_message/);
  assert.match(workspace, /timeZone:\s*"Asia\/Kolkata"[\s\S]*timeZoneName:\s*"short"/);
  assert.match(workspace, /formatMarketTimestamp\(holding\.price_as_of\)/);
});

test("portfolio transaction form prevents duplicate submits and constrains sells to held quantity", () => {
  assert.match(workspace, /transactionSubmission\.current\) return/);
  assert.match(workspace, /transactionSubmission\.current = true/);
  assert.match(workspace, /disabled=\{loading \|\| savingTransaction/);
  assert.match(workspace, /max=\{side === "SELL" \? selectedHolding\?\.quantity : undefined\}/);
  assert.match(workspace, /No matching shares are currently held/);
});

test("portfolio creation form fits narrow mobile viewports without implicit grid overflow", () => {
  assert.match(styles, /@media \(max-width: 680px\)[\s\S]*?\.portfolio-create-form \{ grid-template-columns: minmax\(0, 1fr\); \}/);
});
