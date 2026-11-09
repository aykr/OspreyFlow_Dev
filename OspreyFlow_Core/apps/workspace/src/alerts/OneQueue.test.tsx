// @vitest-environment jsdom
// ADR-146 (L2.10) in the Glass: the one queue's markings (a routed team, a suppressed alert, one
// taken back by a revert), *what fired it* on a watch alert, the team lead's tools (offered to the
// lead alone, as the server says), *What raises alerts*, and the Glass's own *Watch for this*,
// *Save as a watch* and *Raise an alert…*, each refusal said in the Conduit's words.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertQueue, markWords } from "./AlertQueue";
import { AlertSourcesPanel } from "./AlertSourcesPanel";
import { RaiseAlert, SaveAsWatch, WatchForThis } from "../watches/GlassWatchActions";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const API = { apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" };
const base = { owner_id: "o", mode: "full", investigation_id: "c1", assignee: null, created_at: "2026-11-01T07:00:00Z", referent_node_ids: ["n1"] };
const node = {
  id: "n1", type: "Endpoint", properties: { value_normalised: "+447700900310" },
  provenance: { state: "asserted", sources: [{ document_id: "in/calls.csv", locator: "row 3", excerpt_hash: "a" }], first_seen: "2026-01-01T00:00:00Z" },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
  audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
}; // prettier-ignore

function serve(routes: Record<string, unknown>, calls: { path: string; body?: unknown }[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/investigations/c1/", "");
      calls.push({ path: `${init?.method ?? "GET"} ${path}`, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const found = routes[`${init?.method ?? "GET"} ${path}`];
      if (found instanceof Response) return found;
      return found === undefined ? json(404, {}) : json(200, found);
    }),
  );
  return calls;
}

describe("the one queue's markings", () => {
  it("marks an alert taken back by a revert, and a suppressed one until its day (G12, Amendment 1)", () => {
    expect(markWords({ ...base, id: "a", rule_id: "typology:r", status: "closed", disposition: null } as never, false)).toBe(
      "Taken back: the load that raised it was reverted",
    );
    expect(markWords({ ...base, id: "a", rule_id: "typology:r", status: "open", suppressed_until: "2026-12-01", suppress_reason: "known pattern" } as never, true)).toMatch(
      /^Suppressed until .*: known pattern$/,
    );
    expect(markWords({ ...base, id: "a", rule_id: "typology:r", status: "closed", disposition: "false_positive" } as never, false)).toBeNull();
  });

  it("says a routed alert is its team's alone, by the team's name", async () => {
    const routed = { alert: { ...base, id: "r1", rule_id: "typology:x", typology: "sentence", status: "open", routed_team: "team-7" }, summary: "Routed", kind: "typology", severity: "medium", audience: "team", team: "team-7", team_name: "Prison intel" };
    serve({ "GET alert-queue": [routed] });
    render(<AlertQueue {...API} level="editor" accountId="me" onCanvas={vi.fn()} />);
    const row = (await screen.findByText("Routed")).closest("li")!;
    expect(within(row).getByText(/Team Prison intel only/)).toBeTruthy();
  });
});

describe("an alert's detail", () => {
  const hotlistRow = { alert: { ...base, id: "h1", rule_id: "hotlist:hl", status: "open" }, summary: "A hotlisted identifier appeared", kind: "hotlist", severity: "high", audience: "owner", team: null };

  it("says what fired a watch alert: the hotlist's entry and the file and row", async () => {
    serve({
      "GET alert-queue": [hotlistRow],
      "GET alert-queue/h1": { ...hotlistRow, nodes: [node], edges: [], transactions: [], hotlist: { identifier: "07700 900310", kept_as_written: false, review_date: "2027-01-31" }, fired_on: [{ type: "Endpoint", label: "+447700900310", files: [{ name: "calls.csv", row: 3 }], more_files: 0 }] },
    });
    render(<AlertQueue {...API} level="editor" accountId="me" onCanvas={vi.fn()} openAlertId="h1" />);
    const fired = await screen.findByRole("region", { name: "What fired it" });
    expect(within(fired).getByText(/Your hotlist entry 07700 900310/)).toBeTruthy();
    expect(within(fired).getByText(/calls\.csv, row 4/)).toBeTruthy();
  });

  const routed = { alert: { ...base, id: "r1", rule_id: "typology:x", typology: "sentence", status: "open", routed_team: "team-7" }, summary: "Routed", kind: "typology", severity: "medium", audience: "team", team: "team-7" };

  it("offers the lead's tools to the team's lead alone, and suppresses with a reason and a day", async () => {
    const calls = serve({
      "GET alert-queue": [routed],
      "GET alert-queue/r1": { ...routed, nodes: [node], edges: [], transactions: [], lead: true, team_name: "Prison intel" },
      "GET alert-teams": [{ role_id: "team-7", display_name: "Prison intel", lead: true, members: ["member-2"] }],
      "POST alert-queue/r1/suppress": { ...routed.alert, suppressed_until: "2026-12-01" },
      "POST alert-queue/r1/assign": { ...routed.alert, assignee: "member-2", status: "claimed" },
    });
    render(<AlertQueue {...API} level="editor" accountId="me" onCanvas={vi.fn()} openAlertId="r1" />);
    const tools = await screen.findByRole("group", { name: "As the team's lead" });
    fireEvent.change(await within(tools).findByRole("combobox", { name: "Give to (a member of the team)" }), { target: { value: "member-2" } });
    fireEvent.click(within(tools).getByRole("button", { name: "Give to the member" }));
    await waitFor(() => expect(calls.some((c) => c.path === "POST alert-queue/r1/assign")).toBe(true));
    const suppress = within(await screen.findByRole("group", { name: "As the team's lead" })).getByRole("button", { name: "Suppress until…" }) as HTMLButtonElement;
    expect(suppress.disabled).toBe(true);
    const group = screen.getByRole("group", { name: "As the team's lead" });
    fireEvent.change(within(group).getByLabelText("Suppress until (at most 90 days ahead)"), { target: { value: "2026-12-01" } });
    fireEvent.change(within(group).getByLabelText("Why, in words: the reason for suppressing it"), { target: { value: "a known pattern" } });
    fireEvent.click(within(group).getByRole("button", { name: "Suppress until…" }));
    await waitFor(() => expect(calls.find((c) => c.path === "POST alert-queue/r1/suppress")?.body).toEqual({ until: "2026-12-01", reason: "a known pattern" }));
  });

  it("offers a member who is not the lead no lead tools", async () => {
    serve({ "GET alert-queue": [routed], "GET alert-queue/r1": { ...routed, nodes: [node], edges: [], transactions: [], lead: false } });
    render(<AlertQueue {...API} level="editor" accountId="me" onCanvas={vi.fn()} openAlertId="r1" />);
    await screen.findByRole("region", { name: "What fired this alert" });
    expect(screen.queryByRole("group", { name: "As the team's lead" })).toBeNull();
  });
});

describe("What raises alerts", () => {
  it("lists every rule and watch with its counts, filters by a column, and lists a suppression beside its rule", async () => {
    serve({
      "GET alert-sources": {
        sources: [
          { id: "r", rule_id: "typology:r", name: "Listed people", source: "rule", kind: "rule", maker: "a", maker_name: "A. Field", owner: "Prison intel", state: "live", alerts_30_days: 4, not_of_interest: 0.25, last_fired_at: "2026-11-01T07:00:00Z", suppressed: [{ alert_id: "x", until: "2026-12-01", reason: "known", by: "lead" }] },
          { id: "h", rule_id: "hotlist:h", name: "Hotlist 07700 900310", source: "watch", kind: "hotlist", maker: "me", owner: "me", state: "live", expires_on: "2027-01-31", alerts_30_days: 1, not_of_interest: null, suppressed: [] },
        ],
      },
    });
    render(<AlertSourcesPanel {...API} />);
    const table = await screen.findByRole("table", { name: "Rules and watches" });
    expect(within(table).getByText("Listed people")).toBeTruthy();
    expect(within(table).getByText("25%")).toBeTruthy();
    expect(within(table).getByText(/One alert suppressed until .*: known/)).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Filter by source" }), { target: { value: "watch" } });
    await waitFor(() => expect(within(table).queryByText("Listed people")).toBeNull());
    expect(within(table).getByText("Hotlist 07700 900310")).toBeTruthy();
  });

  it("names the owner and the suppressor, never by their identity-provider ids (ADR-106, rule 7)", async () => {
    const subject = "6f1c2a9e-idp-subject";
    const lead = "9b2d7c41-idp-subject";
    serve({
      "GET alert-sources": {
        sources: [
          { id: "h", rule_id: "hotlist:h", name: "Hotlist 07700 900310", source: "watch", kind: "hotlist", maker: subject, maker_name: "Mo Maker", owner: subject, owner_name: "Mo Maker", state: "live", alerts_30_days: 1, suppressed: [{ alert_id: "x", until: "2026-12-01", reason: "known", by: lead, by_name: "Lee Lead" }] },
          { id: "r", rule_id: "typology:r", name: "Routed", source: "rule", kind: "rule", maker: subject, maker_name: "Mo Maker", owner: "team-7", owner_name: "Prison intel", state: "live", alerts_30_days: 0, suppressed: [] },
        ],
      },
    });
    render(<AlertSourcesPanel {...API} />);
    const table = await screen.findByRole("table", { name: "Rules and watches" });
    expect(within(table).getAllByText("Mo Maker").length).toBe(3);
    expect(within(table).getByText("Prison intel")).toBeTruthy();
    expect(within(table).getByText(/suppressed until .* by Lee Lead: known/)).toBeTruthy();
    expect(table.textContent).not.toContain(subject);
    expect(table.textContent).not.toContain(lead);
    expect(table.textContent).not.toContain("team-7");
  });
});

describe("made in the Glass", () => {
  it("watches an entity by its identifier, and offers nothing for one with none", async () => {
    const calls = serve({ "POST hotlists": { id: "h" } });
    render(<WatchForThis {...API} node={node} />);
    fireEvent.click(screen.getByRole("button", { name: "Watch for this" }));
    await waitFor(() => expect(calls.find((c) => c.path === "POST hotlists")?.body).toMatchObject({ identifier: "+447700900310" }));
    cleanup();
    render(<WatchForThis {...API} node={{ id: "p", properties: { name: "Okafor" } }} />);
    expect(screen.queryByRole("button", { name: "Watch for this" })).toBeNull();
  });

  it("saves a saved pattern as a watch, and offers nothing before it is saved", async () => {
    const calls = serve({ "POST monitors": { id: "m" } });
    render(<SaveAsWatch {...API} patternId="p1" />);
    fireEvent.click(screen.getByRole("button", { name: "Save as a watch" }));
    await waitFor(() => expect(calls.find((c) => c.path === "POST monitors")?.body).toEqual({ pattern_id: "p1" }));
    expect(await screen.findByRole("status")).toBeTruthy();
    cleanup();
    render(<SaveAsWatch {...API} patternId={null} />);
    expect(screen.queryByRole("button", { name: "Save as a watch" })).toBeNull();
  });

  it("raises an alert to the dataset, and says the Conduit's refusal of a drawn item in its words", async () => {
    const refusal = json(409, { detail: { code: "not_the_datasets_own", message: "A dataset alert may cite only the dataset's own items." } });
    const calls = serve({
      "GET /v1/investigations": [{ id: "c1", name: "Case", level: "editor", created_at: "", created_by: "", datasets: ["Prison intel"], dataset_ids: ["ds-1"] }],
      "POST raised-alerts": refusal,
    });
    render(<RaiseAlert {...API} nodeIds={["n1", "drawn-1"]} foundBy="the query 'x'" />);
    fireEvent.click(screen.getByRole("button", { name: "Raise an alert…" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Title of the alert" }), { target: { value: "Same flat" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Why, in words: the reason for the alert" }), { target: { value: "three companies" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Where the alert goes" }), { target: { value: "dataset" } });
    await waitFor(() => expect(calls.some((c) => c.path === "GET /v1/investigations")).toBe(true));
    await waitFor(() => expect((screen.getByRole("button", { name: "Raise the alert" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Raise the alert" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "A dataset alert may cite only the dataset's own items.");
    expect(calls.find((c) => c.path === "POST raised-alerts")?.body).toMatchObject({ to: "dataset", dataset_id: "ds-1", node_ids: ["n1", "drawn-1"], found_by: "the query 'x'" });
  });
});
