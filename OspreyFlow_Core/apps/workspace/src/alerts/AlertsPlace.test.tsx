// @vitest-environment jsdom
// ADR-109 phase B: the Alerts place. The queue shows what the Conduit returns, named, never by id;
// an alert explains itself with its transactions; closing one needs a reason; triage and rule
// deployment are offered only at the level that may do them; a refusal is said in words.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertsPlace } from "./AlertsPlace";
import { describeParams, ruleInput } from "./RulesPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function account(id: string, name: string) {
  return {
    id,
    type: "Account",
    properties: { account_number: name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  };
}

const ALERT = {
  id: "a1", rule_id: "typology:r1", owner_id: "deployer", mode: "full",
  referent_node_ids: ["n1", "n2"], investigation_id: "c1", created_at: "2026-09-01T12:00:00Z",
  typology: "structuring", words: "4 movements from n1 to n2", edge_ids: ["e1"], event_ids: ["v1"],
  window: { valid_from: "2026-09-01T09:00:00Z", valid_to: "2026-09-01T12:00:00Z" },
  trigger: "pre_commit", alert_node_id: "al1", status: "open", assignee: null,
};  // prettier-ignore

function serve(level: "viewer" | "editor" | "author", extra: (path: string, init?: RequestInit) => Response | null = () => null) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/investigations/c1/", "");
      calls.push(`${init?.method ?? "GET"} ${path}`);
      const answered = extra(path, init);
      if (answered) return answered;
      if (path === "/v1/investigations") return json(200, [{ id: "c1", name: "Case", level, created_at: "", created_by: "" }]);
      if (path === "alert-queue") return json(200, [{ alert: ALERT, summary: "4 movements from GB-MULE to GB-HUB" }]);
      if (path === "alert-queue/a1")
        return json(200, {
          alert: ALERT,
          summary: "4 movements from GB-MULE to GB-HUB",
          nodes: [account("n1", "GB-MULE"), account("n2", "GB-HUB")],
          edges: [],
          transactions: [{ event_id: "v1", edge_id: "e1", source_id: "n1", target_id: "n2", occurred_at: "2026-09-01T09:00:00Z", amount: 9500 }],
        });
      if (path === "rules") return json(200, []);
      return json(404, {});
    }),
  );
  return calls;
}

function place(onCanvas = vi.fn()) {
  render(
    <AlertsPlace apiBaseUrl="http://x" bearerToken="t" investigationId="c1" accountId="me" isAdministrator={false} onCanvas={onCanvas} />,
  );
  return onCanvas;
}

describe("the Alerts place", () => {
  it("lists the queue by name and explains an alert with its transactions", async () => {
    serve("viewer");
    place();
    const row = await screen.findByRole("button", { name: /Open alert: Structuring — 4 movements from GB-MULE to GB-HUB/ });
    expect(screen.queryByText(/n1/)).toBeNull();
    fireEvent.click(row);
    expect(await screen.findByRole("table", { name: "Transactions this alert cites" })).toBeTruthy();
    expect(screen.getByText("9,500")).toBeTruthy();
    expect(screen.getByText("GB-MULE")).toBeTruthy();
  });

  it("offers no triage to a Viewer", async () => {
    serve("viewer");
    place();
    fireEvent.click(await screen.findByRole("button", { name: /Open alert/ }));
    await screen.findByRole("table", { name: "Transactions this alert cites" });
    expect(screen.queryByRole("button", { name: "Claim" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Close as true positive" })).toBeNull();
  });

  it("closes an alert only with a reason, and sends the reason", async () => {
    const bodies: string[] = [];
    serve("editor", (path, init) => {
      if (path === "alert-queue/a1/disposition") {
        bodies.push(String(init?.body));
        return json(200, { ...ALERT, status: "closed", disposition: "true_positive" });
      }
      return null;
    });
    place();
    fireEvent.click(await screen.findByRole("button", { name: /Open alert/ }));
    const close = await screen.findByRole("button", { name: "Close as true positive" });
    expect((close as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Reason for closing"), { target: { value: "Matches the SAR" } });
    expect((close as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(close);
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(JSON.parse(bodies[0] ?? "{}")).toEqual({ disposition: "true_positive", reason: "Matches the SAR" });
  });

  it("puts an alert on the canvas and hands over its nodes to highlight", async () => {
    const delta = { seq: 2, op: "add", nodes: [], edges: [] };
    serve("editor", (path) => (path === "alert-queue/a1/canvas" ? json(200, { delta, added_nodes: 3, added_links: 3 }) : null));
    const onCanvas = place();
    fireEvent.click(await screen.findByRole("button", { name: /Open alert/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Show on the canvas" }));
    await waitFor(() => expect(onCanvas).toHaveBeenCalled());
    expect(onCanvas.mock.calls[0]?.[1]).toEqual(["n1", "n2"]);
  });

  it("says in words when someone else got to the alert first", async () => {
    serve("editor", (path) => (path === "alert-queue/a1/claim" ? json(409, { error: "alert_moved_on" }) : null));
    place();
    fireEvent.click(await screen.findByRole("button", { name: /Open alert/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Claim" }));
    expect(await screen.findByText("Someone else has already claimed or closed this alert.")).toBeTruthy();
  });

  it("offers deployment to an Author only", async () => {
    serve("editor");
    place();
    fireEvent.click(await screen.findByRole("tab", { name: "Rules" }));
    expect(await screen.findByText("A case Author deploys and retires rules.")).toBeTruthy();
    cleanup();
    serve("author");
    place();
    fireEvent.click(await screen.findByRole("tab", { name: "Rules" }));
    expect(await screen.findByRole("form", { name: "Deploy a rule" })).toBeTruthy();
  });
});

describe("a rule's parameters", () => {
  it("are sent as numbers in the typology's closed shape", () => {
    expect(ruleInput(" Pass-through ", "rapid_movement", { within_hours: "24" }, "pre_commit", 2000)).toEqual({
      name: "Pass-through",
      params: { typology: "rapid_movement", within_hours: 24, keep_fraction: 0.8 },
      trigger: "pre_commit",
      budget_ms: 2000,
    });
  });

  it("for a drawn pattern carry the saved pattern, and always run after commit", () => {
    expect(ruleInput("Drawn", "pattern", {}, "pre_commit", 5000, {}, [], "pat-1").params).toEqual({
      typology: "pattern",
      max_matches: 200,
      pattern_id: "pat-1",
    });
  });

  it("are described in words", () => {
    const rule = {
      id: "r", investigation_id: "c1", owner_id: "o", name: "S", created_at: "",
      params: { typology: "structuring", threshold: 10000, window_days: 7, minimum_count: 3 },
    };  // prettier-ignore
    expect(describeParams(rule as never)).toBe("3+ movements each under 10,000, summing past it, within 7 day(s)");
  });
});
