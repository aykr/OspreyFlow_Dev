// Alerts in reporting (ADR-134 decisions 1 and 3), drawn from synthetic data with no server: a
// report pack holding an open alert whose match is still inferred, a trend over alerts split by
// rule, and an alert closed as a true match — each as the Glass shows a pack item. For the
// every-harness axe scan (`a11y/every-harness.spec.ts`, which finds this page by its directory) and
// for the Product Overview deck's screens, in both brands (`?brand=govuk`). `?show=alert` draws the
// open alert alone and `?show=trend` the trend alone. The names and numbers are invented (rule 9).
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import type { PackItem } from "../../../packages/schemas/generated";
import { PackItemView } from "../src/reports/PackItemView";
import { WITHHELD_ITEMS_SENTENCE } from "../src/reports/packText";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const base = { added_by: "analyst-1", added_at: "2026-10-30T09:00:00Z" };

const OPEN_ALERT: PackItem = {
  id: "i1", kind: "alert", marking: "OFFICIAL-SENSITIVE", ...base,
  alert: {
    alert_id: "a-rap", kind: "typology", severity: "high", typology: "rapid_movement",
    explanation: "£48,600 in to GB-MULE-0042 and 92% of it out again within 36 hours",
    raised_at: "2026-10-28T16:20:00Z",
    entities: [
      { node_id: "n1", entity_type: "Account", name: "GB-MULE-0042" },
      { node_id: "n2", entity_type: "Organisation", name: "Harbour Freight Ltd" },
    ],
    links: [{ edge_id: "e1", type: "TRANSACTED", source_name: "GB-MULE-0042", target_name: "GB-HUB-0007" }],
    transactions: [
      { occurred_at: "2026-10-27T10:05:00Z", amount: 48600, source_name: "Harbour Freight Ltd", target_name: "GB-MULE-0042" },
      { occurred_at: "2026-10-28T09:40:00Z", amount: 44700, source_name: "GB-MULE-0042", target_name: "GB-HUB-0007" },
    ],
    status: "open", outcome: null, reason: null, match: "inferred", node_ids: ["n1", "n2"],
  },
};  // prettier-ignore

const CLOSED_ALERT: PackItem = {
  id: "i3", kind: "alert", marking: "OFFICIAL", ...base,
  alert: {
    alert_id: "a-hot", kind: "hotlist", severity: "high", typology: null,
    explanation: "A hotlisted identifier appeared: 07700 900310", hotlist_entry: "07700 900310",
    raised_at: "2026-10-21T08:10:00Z",
    entities: [{ node_id: "n3", entity_type: "Endpoint", name: "07700 900310" }],
    links: [], transactions: [],
    status: "closed", outcome: "true_positive", reason: "Seen with the subject on 21 October; confirmed by the desk", match: "confirmed",
    node_ids: ["n3"],
  },
};  // prettier-ignore

const WEEKS = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"];
const RAISED: Record<string, number[]> = {
  "Rapid movement over £9,000": [1, 0, 2, 1, 3, 2, 4, 3],
  "Structuring under £10,000": [2, 1, 1, 2, 1, 3, 2, 2],
  Hotlists: [0, 1, 0, 1, 2, 1, 3, 2],
  Monitors: [1, 0, 1, 0, 0, 1, 1, 2],
};

const ALERT_TREND: PackItem = {
  id: "i2", kind: "trend", marking: "OFFICIAL-SENSITIVE", ...base, trend_id: "t-alerts",
  trend: {
    definition: { title: "Alerts raised per week, by rule", source: "alerts", event_types: [], measure: "count", measure_field: null,
                  interval: "week", weeks: 8, group_by: "rule", filters: [] },
    result: {
      interval: "week", measure: "count",
      points: WEEKS.flatMap((period_start, i) => Object.entries(RAISED).map(([series, counts]) => ({ period_start, series, value: counts[i] ?? 0 }))),
      series: Object.keys(RAISED).sort(), total: 54, events: 54, unvalued: 0,
    },
    as_of: "2026-11-01T08:00:00Z", window_start: "2026-09-06T08:00:00Z", marking: "OFFICIAL-SENSITIVE",
  },
};  // prettier-ignore

const show = new URLSearchParams(window.location.search).get("show");
const items = show === "alert" ? [OPEN_ALERT] : show === "trend" ? [ALERT_TREND] : [OPEN_ALERT, ALERT_TREND, CLOSED_ALERT];

createRoot(document.getElementById("root")!).render(
  <main style={{ background: "var(--surface-app)", color: "var(--text-primary)", padding: "var(--sp-16)", display: "grid", gap: "var(--sp-12)" }}>
    <h1 className="value" style={{ margin: 0 }}>Weekly monitoring review</h1>
    <p className="label" style={{ margin: 0 }}>Draft pack · Marked OFFICIAL-SENSITIVE</p>
    {show === null && <p style={{ margin: 0 }}>{WITHHELD_ITEMS_SENTENCE}</p>}
    {items.map((item) => (
      <PackItemView key={item.id} item={item} />
    ))}
  </main>,
);
