// Admin › Running › Operations' figures (ADR-141; L1.7), mounted alone and served by the page itself:
// for `operations-figures.spec.ts` (rule 13) and the every-harness axe scan, in both themes and under
// GOV.UK (`?brand=govuk`). Every request is recorded on `window.__asked`. `?quota=refused` answers a
// quota's save 403, as the Conduit does a reader without Administer system. Synthetic data (rule 9).
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { OperationsFigures } from "../src/admin/OperationsFigures";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const params = new URLSearchParams(window.location.search);
const asked: { method: string; path: string; body?: string }[] = [];
(window as unknown as { __asked: typeof asked }).__asked = asked;
let quotas = [{ scope: "dataset", key: "harbour-extract", runs_per_day: 1, alert_at_share: 0.8 }];

const rollup = () => ({
  days: 7,
  units: ["unit-1"],
  rows: [
    { day: "2026-11-10", pipeline_id: "r-calls", pipeline_label: "Wing phone calls", unit: "unit-1", trigger: "external",
      runs: 2, succeeded: 1, refused: 1, failed: 0, wall_ms: 4200, rows_read: 120, graph_writes: 30, withheld: false },
    { day: "2026-11-09", pipeline_id: "r-visits", pipeline_label: "Visits", unit: "unit-1", trigger: "schedule",
      runs: 1, succeeded: 1, refused: 0, failed: 0, wall_ms: 900, rows_read: null, graph_writes: null, withheld: true },
  ],
  scheduler: { skipped: 1, missed: 0, running_now: 0, paused: [],
    refused: [{ reason: "the dataset's quota of 1 run a day is used (1 run today)", count: 1 }] },
  external: [{ run_id: "SYN-RUN-1", pipeline_label: "Wing phone calls", service_identity: "syn-airflow",
    ran_as_name: "Sam Example", started_at: "2026-11-10T09:00:00Z", outcome: "succeeded", wall_ms: 2100, withheld: false }],
  quotas,
});  // prettier-ignore

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  const method = init?.method ?? "GET";
  asked.push({ method, path, ...(typeof init?.body === "string" ? { body: init.body } : {}) });
  const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  if (path === "/v1/admin/operations/runs") return reply(rollup());
  const quota = path.match(/^\/v1\/admin\/operations\/quotas\/(dataset|unit)\/(.+)$/);
  if (quota && method === "PUT") {
    if (params.get("quota") === "refused") return reply({ detail: "right_required" }, 403);
    const body = JSON.parse(String(init?.body)) as { runs_per_day: number | null };
    const saved = { scope: quota[1]!, key: decodeURIComponent(quota[2]!), runs_per_day: body.runs_per_day, alert_at_share: 0.8 };
    quotas = [...quotas.filter((q) => !(q.scope === saved.scope && q.key === saved.key)), saved];
    return reply(saved);
  }
  return reply({ detail: "not_found" }, 404);
};

createRoot(document.getElementById("root")!).render(
  <OperationsFigures api={{ apiBaseUrl: "http://harness", bearerToken: "t" }} />,
);
