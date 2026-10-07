// Case datasets keyboard harness (ADR-099): a new case's "Data the case reads" and a case's own
// "Data this case reads", as the case picker and the Cases drawer render them. `case-datasets.spec.ts`
// intercepts the routes; what the forms hand back is on `window.__CASE_DATASETS__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { CaseDatasets } from "../src/investigation/CaseDatasets";
import { NewCaseForm } from "../src/investigation/NewCaseForm";

declare global {
  interface Window {
    __CASE_DATASETS__?: { created: string | null; changed: number };
  }
}

window.__CASE_DATASETS__ = { created: null, changed: 0 };

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <div style={{ display: "grid", gap: "24px" }}>
    <NewCaseForm
      apiBaseUrl="http://keyboard-test.invalid"
      bearerToken="unused"
      inputLabel="Case name"
      onCreated={(id) => {
        window.__CASE_DATASETS__!.created = id;
      }}
    />
    <CaseDatasets
      apiBaseUrl="http://keyboard-test.invalid"
      bearerToken="unused"
      investigationId="c1"
      onChanged={() => {
        window.__CASE_DATASETS__!.changed += 1;
      }}
    />
  </div>,
);
