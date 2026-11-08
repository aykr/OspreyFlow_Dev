// Case datasets keyboard harness (ADR-099, ADR-126): a new case's "Data the case reads" and "Domain
// models", and a case's own "Data this case reads" and "Domain models", as the case picker and the
// Cases drawer render them. `case-datasets.spec.ts` intercepts the routes; what the forms hand back
// is on `window.__CASE_DATASETS__`. Once a case is made, its own Domain models are drawn under
// "Made case", read back through the listing as the Glass reads any case.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { CaseDomains } from "../src/investigation/CaseDomains";
import { CaseSettings } from "../src/investigation/CaseSettings";
import { NewCaseForm } from "../src/investigation/NewCaseForm";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __CASE_DATASETS__?: { created: string | null; changed: number };
  }
}

window.__CASE_DATASETS__ = { created: null, changed: 0 };

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// Under `?brand=govuk` the forms are drawn in the GOV.UK brand (ADR-132), for the axe scan's third
// variant; `?choice=existing` opens the new case's form on "Use an existing dataset", so the scan
// sees the dataset radios too (ADR-099 Amendment 12).
await applyHarnessBrand();
const initialChoice = new URLSearchParams(window.location.search).get("choice") === "existing" ? "existing" : "new";
// The axe scan serves no routes; in that state the harness answers the dataset list itself, with
// synthetic datasets (rule 9), so the radios it scans are drawn. A keyboard spec's own `page.route`
// answers first and is unaffected.
if (initialChoice === "existing") {
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) =>
    String(input).endsWith("/v1/datasets")
      ? new Response(
          JSON.stringify([
            { id: "ds-a", name: "Carrier A intake", owning_unit: "unit-1", kind: "source" },
            { id: "ds-b", name: "Both carriers", owning_unit: "unit-1", kind: "composite", members: ["ds-a", "ds-c"] },
          ]),
          { status: 200 },
        )
      : realFetch(input, init);
}

function Harness() {
  const [made, setMade] = useState<string | null>(null);
  return (
    <div style={{ display: "grid", gap: "24px" }}>
      <NewCaseForm
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        inputLabel="Case name"
        initialChoice={initialChoice}
        onCreated={(id) => {
          window.__CASE_DATASETS__!.created = id;
          setMade(id);
        }}
      />
      {/* As the Cases drawer renders them: one listing read for both, read again after a change. */}
      <CaseSettings
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        investigationId="c1"
        onChanged={() => {
          window.__CASE_DATASETS__!.changed += 1;
        }}
      />
      {made && (
        <section aria-label="Made case">
          <CaseDomains apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" investigationId={made} />
        </section>
      )}
    </div>
  );
}

createRoot(container).render(<Harness />);
