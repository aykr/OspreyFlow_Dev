// Rules and Monitoring's keyboard harness (ADR-146 decisions 2 and 6, `CLAUDE.md` rule 13): the real
// `RulesPlace` wired to the real router (`shell/router.ts`) and the real address hook
// (`alerts/address.ts`), as `App.tsx` wires them, so opening an alert gives it its address, Back
// leaves it, and an address opens its alert. The page answers its own reads (rule 9: synthetic).
// `?address=<id>` starts on that alert's address; `a1` is this case's, `a-other` is another case's
// (its reload into that case is recorded on `window.__RULES__.went`, not made), and any other id is
// answered as missing, as the Conduit answers an alert the reader may not see. `?brand=govuk` draws
// it in the GOV.UK frame.
import { createRoot } from "react-dom/client";
import { useEffect } from "react";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { BrandFrame } from "../src/brand/BrandFrame";
import { PLAIN_APPEARANCE } from "../src/brand/brand";
import { openAlertInItsCase, useAlertAtAddress } from "../src/alerts/address";
import { RulesPlace } from "../src/alerts/RulesPlace";
import { alertPath, navigate, useAddress } from "../src/shell/router";

declare global {
  interface Window {
    __RULES__?: { went: string[] };
  }
}
window.__RULES__ = { went: [] };

const brand = await applyHarnessBrand();
const params = new URLSearchParams(location.search);
const start = params.get("address");
if (start) history.replaceState(null, "", `${alertPath(start)}${location.search}`);

const NODE = (id: string, name: string) => ({
  id, type: "Account", properties: { name },
  provenance: { state: "asserted", sources: [], first_seen: "2026-10-01T00:00:00Z" },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-a", owning_unit: "unit-a" },
  audit: { created_at: "2026-10-01T00:00:00Z", created_by: "seed", revision: 1 },
}); // prettier-ignore
const ALERT = {
  id: "a1", rule_id: "typology:r1", owner_id: "analyst-1", mode: "full", investigation_id: "inv-1", status: "open",
  assignee: null, typology: "structuring", referent_node_ids: ["n1"], created_at: "2026-11-01T09:00:00Z",
}; // prettier-ignore
const ROW = { alert: ALERT, summary: "4 movements from GB-MULE-0042 to GB-HUB-0007", kind: "typology", severity: "medium", audience: "case", team: null };
const EXPLAINED = { ...ROW, nodes: [NODE("n1", "GB-MULE-0042")], edges: [], transactions: [] };

function answer(path: string): unknown {
  if (path === "/v1/investigations") return [{ id: "inv-1", name: "Operation Ledger", level: "author", created_at: "", created_by: "" }];
  if (path === "/v1/alerts/a1") return { investigation_id: "inv-1", explanation: EXPLAINED };
  if (path === "/v1/alerts/a-other") return { investigation_id: "inv-2", explanation: { ...EXPLAINED, alert: { ...ALERT, id: "a-other" } } };
  if (path.startsWith("/v1/alerts/")) return null;
  const local = path.replace("/v1/investigations/inv-1/", "");
  if (local === "alert-queue") return [ROW];
  if (local === "alert-queue/a1") return EXPLAINED;
  if (local === "alert-assignees") return [{ id: "analyst-1", name: "Dana Analyst" }];
  if (local === "alerts") return { alerts: [] };
  if (local === "rules") return [];
  if (local === "patterns") return { patterns: [] };
  if (local === "hotlists") return { hotlists: [], audience_default: "only_me", audience_editable: true };
  if (local === "monitors") return { monitors: [] };
  if (local === "held-rows") return [];
  if (local === "rules/audit") return { entries: [], total: 0, offset: 0, limit: 50 };
  if (path === "/v1/screening-lists") return { lists: [] };
  if (path === "/v1/ontology") return { entity_types: [], edge_types: [] };
  return null;
}

window.fetch = async (input: RequestInfo | URL) => {
  const body = answer(new URL(String(input)).pathname);
  return new Response(JSON.stringify(body ?? { error: "alert_not_found" }), { status: body === null ? 404 : 200 });
};

function Harness() {
  const address = useAddress();
  const alertId = address.kind === "alert" ? address.alertId : null;
  const state = useAlertAtAddress("http://rules-harness.invalid", "unused", alertId);
  useEffect(() => {
    if (state?.status === "found" && alertId && state.caseId !== "inv-1") {
      openAlertInItsCase(alertId, state.caseId, (url) => window.__RULES__!.went.push(url));
    }
  }, [state, alertId]);
  return (
    <RulesPlace
      apiBaseUrl="http://rules-harness.invalid"
      bearerToken="unused"
      investigationId="inv-1"
      accountId="analyst-1"
      isAdministrator={false}
      onCanvas={() => undefined}
      address={alertId && state ? { alertId, state } : null}
      onOpenAlert={(id) => navigate(id ? alertPath(id) : "/keyboard/rules-place-harness.html")}
    />
  );
}

createRoot(document.getElementById("root")!).render(
  <BrandFrame
    appearance={
      brand === "govuk"
        ? { brand: "govuk", serviceName: "Prison Intelligence", organisation: "Ministry of Examples", phase: "beta" }
        : PLAIN_APPEARANCE
    }
  >
    <Harness />
  </BrandFrame>,
);
