// @vitest-environment jsdom
// Step 9d finding 2: the Ledger's screening alert (K1) listed "Sofia Ruiz · Person" twice in its
// detail. The alert stores no duplicate: it cites two nodes (`kyc_rules.screening_finding`), the
// customer and the list's own entry for the listed party, joined by the inferred `SAME_AS` the
// alert also cites. The entity is never merged with the list entry (rule 6), and the match stays a
// suggestion until a person confirms it (rule 5), so both are shown — but the list's entry is said
// to be the list's, so the two lines no longer read the same.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertsPlace } from "./AlertsPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const provenance = { state: "asserted", sources: [], first_seen: "2026-10-06T00:00:00Z" };
const handling = { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" };
const audit = { created_at: "2026-10-06T00:00:00Z", created_by: "seed", revision: 1 };

/** The customer, as the Ledger's KYC recipe loads her (`ledger_kyc_recipe.yaml`). */
const CUSTOMER = { id: "n-customer", type: "Person", provenance, handling, audit,
  properties: { family_name: "Ruiz", given_names: "Sofia", date_of_birth: "2001-06-14" } };  // prettier-ignore
/** The list's entry for her, as `kyc_rules._listed_write` writes it from "RUIZ, Sofia". */
const LISTED = { id: "n-listed", type: "Person", provenance, handling, audit,
  properties: { family_name: "Ruiz", given_names: "Sofia", date_of_birth: "2001-06-14", listing: "sanction",
    list_name: "UK Sanctions List (synthetic)" } };  // prettier-ignore
const ALERT_NODE = { id: "n-alert", type: "Alert", provenance, handling, audit, properties: { rule_id: "r-k" } };

const K1 = {
  alert: { id: "k1", owner_id: "admin", mode: "full", investigation_id: "c1", status: "open", assignee: null,
    rule_id: "typology:r-k", typology: "kyc_screening", referent_node_ids: ["n-customer", "n-listed"],
    alert_node_id: "n-alert", created_at: "2026-10-06T09:00:00Z" },
  summary: "Sofia Ruiz: Sofia Ruiz matches “RUIZ, Sofia” on a sanctions list (UK Sanctions List (synthetic)), score 1.00",
  kind: "typology", severity: "high", audience: "case", team: null,
}; // prettier-ignore

function serve() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = new URL(url).pathname.replace("/v1/investigations/c1/", "");
      if (path === "/v1/investigations") return json(200, [{ id: "c1", name: "Case", level: "editor", created_at: "", created_by: "" }]);
      if (path === "alert-queue") return json(200, [K1]);
      if (path === "alert-queue/k1") return json(200, { ...K1, nodes: [CUSTOMER, LISTED, ALERT_NODE], edges: [], transactions: [] });
      if (path === "alert-assignees") return json(200, []);
      if (path === "rules") return json(200, []);
      return json(404, {});
    }),
  );
}

describe("a screening alert's detail", () => {
  it("names the customer once, and the list's entry for the listed party as the list's", async () => {
    serve();
    render(<AlertsPlace apiBaseUrl="http://x" bearerToken="t" investigationId="c1" accountId="me" isAdministrator={false} onCanvas={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Open alert:.*KYC screening/ }));
    const concerns = await screen.findByRole("list", { name: "What this alert concerns" });
    const lines = within(concerns).getAllByRole("listitem").map((li) => li.textContent);
    expect(lines).toEqual(["Sofia Ruiz · Person", "Sofia Ruiz · Person · the entry on UK Sanctions List (synthetic)"]);
    expect(new Set(lines).size).toBe(lines.length);
  });
});
