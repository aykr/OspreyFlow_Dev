// Studio › Sources' connectors and screening lists (ADR-140 Amendment 13) on their own:
// `sources-connectors.spec.ts` intercepts the dataset's and the deployment's routes and walks each part
// by keyboard. `?view=lists` (the default) is the screening lists, `?view=wizard` the register wizard,
// `?view=source` a SQL source's page, `?view=import&template=blank` and `?view=schedule` the import and
// schedule forms drawn open. With `?serve=1` the harness answers its own requests with synthetic data,
// for the axe scans of `a11y/every-harness.spec.ts`; `?manage=1` as whoever may load lists.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import type { DeploymentList, SourceTable } from "../../../packages/schemas/generated";
import { RegisterSourceWizard } from "../src/ingest/sources/RegisterSourceWizard";
import { ImportListForm, ScheduleForm, ScreeningLists } from "../src/ingest/sources/ScreeningLists";
import { SourcePage } from "../src/ingest/sources/SourcePage";
import { applyHarnessBrand } from "./brandHarness";

const API = { apiBaseUrl: "http://keyboard-test.invalid", bearerToken: "unused" };
const SCHEME = {
  name: "uk",
  classification: ["OFFICIAL", "SECRET"],
  handling_codes: { P: { label: "Permitted", dissemination: "permitted" as const } },
};
const SQL_SOURCE: SourceTable = {
  id: "src-bookings", dataset_id: "ds-a", connection_id: "c-sql", name: "Visit bookings",
  location: "/in/uploaded/ds-a/visit_bookings.csv", connector_profile: "generic-csv",
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  legal_basis: "Synthetic demonstration", read: { kind: "sql", table: "nomis.visit_bookings", columns: [] },
  refresh: { trigger: "watch", pattern: "visit_bookings.csv", mode: "incremental", watermark_column: "booking_id" },
  version: 1, created_by: "eng-1", created_at: "2026-11-08T09:00:00Z",
};  // prettier-ignore

declare global {
  interface Window {
    __SOURCES__?: { registered: SourceTable[] };
  }
}

const params = new URLSearchParams(window.location.search);
const view = params.get("view") ?? "lists";
window.__SOURCES__ = { registered: [] };
await applyHarnessBrand();

const LIST: DeploymentList = {
  id: "01OFAC", name: "OFAC SDN (synthetic)", template: "ofac_sdn", location: "lists/SDN.CSV", synthetic: true,
  licence: "US Government work, in the public domain", version: 2, entries: 3, schedule_words: "every day at 05:00",
  created_by: "eng-1", created_at: "2026-11-08T09:00:00Z", updated_at: "2026-11-08T09:05:00Z",
};  // prettier-ignore
const FAILED: DeploymentList = { ...LIST, id: "01CLIENT", name: "Client list", template: "blank", version: 0, entries: 0,
  schedule_words: null, updated_at: null, failure: "row 2 has no reference; nothing of the list was kept" };  // prettier-ignore

if (params.get("serve") === "1") {
  const answers: Record<string, unknown> = {
    "/v1/datasets/ds-a/screening-subscriptions": { lists: [LIST, FAILED], subscribed: ["01OFAC"] },
    "/v1/datasets/ds-a/reference-lists/offered": [
      { id: "rl-est", name: "establishments", kind: "reference", version: 1, deployment_wide: false },
      { id: "01OFAC", name: "OFAC SDN (synthetic)", kind: "screening", version: 2, deployment_wide: true },
    ],
    "/v1/studio/screening-lists": [LIST, FAILED],
    "/v1/ingest/connections": [
      { id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "" },
      { id: "c-sql", kind: "sql", name: "NOMIS replica (synthetic)", created_by: "adm-1", created_at: "" },
    ],
    "/v1/datasets/ds-a/source-files": { root: "/in", files: [] },
    "/v1/datasets/ds-a/sources/src-bookings/profile": { columns: [], rows_sampled: 0 },
    "/v1/datasets/ds-a/sources/src-bookings/lineage": [],
  };
  const manage = params.get("manage") === "1";
  window.fetch = async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname;
    if (path === "/v1/studio/screening-lists" && !manage) return new Response("{}", { status: 403 });
    const body = answers[path];
    return new Response(JSON.stringify(body ?? {}), { status: body === undefined ? 404 : 200 });
  };
}

function Harness() {
  if (view === "wizard") {
    return (
      <RegisterSourceWizard
        api={API}
        datasetId="ds-a"
        scheme={SCHEME}
        registered={[]}
        onCancel={() => undefined}
        onRegistered={(s) => window.__SOURCES__!.registered.push(s)}
      />
    );
  }
  if (view === "import") {
    return <ImportListForm onCancel={() => undefined} onSubmit={() => undefined} initialTemplate={params.get("template") ?? undefined} />;
  }
  if (view === "schedule") {
    return <ScheduleForm list={{ ...LIST, schedule: { every: "weekly", hour: 6, weekday: 3 } }} onCancel={() => undefined} onSubmit={() => undefined} />;
  }
  if (view === "source") {
    return (
      <SourcePage
        api={API}
        datasetId="ds-a"
        source={SQL_SOURCE}
        scheme={SCHEME}
        onBack={() => undefined}
        onChanged={() => undefined}
        onOpenInPipeline={() => undefined}
      />
    );
  }
  return <ScreeningLists api={API} datasetId="ds-a" />;
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(
  <main style={{ padding: "var(--sp-16)" }}>
    <h1 style={{ fontSize: "var(--fs-16)" }}>Sources</h1>
    <Harness />
  </main>,
);
