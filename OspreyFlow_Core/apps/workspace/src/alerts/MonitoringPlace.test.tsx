// @vitest-environment jsdom
// ADR-133 stage (a): the Monitoring place. One queue for every kind of alert (typology, hotlist,
// monitor), each row saying its kind, severity, who may see it and its age; filters by kind,
// severity and status, applied by the server; a case alert given to a member, a shared one only
// claimed; the seven typologies offered as templates; a hotlist's audience chosen where the
// deployment allows, and refused in words where it does not.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ageWords } from "./AlertQueue";
import { AlertsPlace } from "./AlertsPlace";
import { TEMPLATES } from "./templates";
import { HotlistPanel } from "../watches/HotlistPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

/** A queue row's name: "Open alert: High severity, Hotlist — <what it found>", whatever spacing the
 * accessible-name computation gives the hidden joining words. */
function alertName(severity: string, title: string, summary = ""): RegExp {
  const words = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s*");
  return new RegExp(`Open alert:\\s*${words(severity)}\\s*severity,\\s*${words(title)}\\s*—\\s*${words(summary)}`);
}

function person(id: string, name: string) {
  return {
    id,
    type: "Person",
    properties: { name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  };
}

const base = { owner_id: "owner-1", mode: "full", investigation_id: "c1", status: "open", assignee: null };
const ROWS = [
  {
    alert: { ...base, id: "h1", rule_id: "hotlist:hl-1", referent_node_ids: ["n2"], created_at: "2026-11-01T07:00:00Z", team: "unit-a" },
    summary: "A hotlisted identifier appeared: 07700 900310",
    kind: "hotlist", severity: "high", audience: "team", team: "unit-a",
  },
  {
    alert: { ...base, id: "t1", rule_id: "typology:r1", typology: "structuring", referent_node_ids: ["n1"], created_at: "2026-10-30T09:00:00Z" },
    summary: "4 movements from GB-MULE to GB-HUB",
    kind: "typology", severity: "medium", audience: "case", team: null,
  },
  {
    alert: { ...base, id: "m1", rule_id: "monitor:mo-1", referent_node_ids: ["n3"], created_at: "2026-11-01T08:30:00Z" },
    summary: "A watched pattern matched: OKAFOR, Callum",
    kind: "monitor", severity: "medium", audience: "owner", team: null,
  },
]; // prettier-ignore

function serve(level: "viewer" | "editor" | "author", extra: (path: string, init?: RequestInit) => Response | null = () => null) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const parsed = new URL(url);
      const path = parsed.pathname.replace("/v1/investigations/c1/", "");
      calls.push(`${init?.method ?? "GET"} ${path}${parsed.search}`);
      const answered = extra(path, init);
      if (answered) return answered;
      if (path === "/v1/investigations") return json(200, [{ id: "c1", name: "Case", level, created_at: "", created_by: "" }]);
      if (path === "alert-queue") return json(200, ROWS);
      const row = ROWS.find((r) => path === `alert-queue/${r.alert.id}`);
      if (row) return json(200, { ...row, nodes: [person(row.alert.referent_node_ids[0]!, row.summary.split(": ")[1] ?? "x")], edges: [], transactions: [] });
      if (path === "alert-assignees") return json(200, [{ id: "member-1", name: "Priya Shah" }, { id: "me", name: "Me" }]);
      if (path === "rules") return json(200, []);
      if (path === "patterns") return json(200, { patterns: [] });
      return json(404, {});
    }),
  );
  return calls;
}

function place() {
  render(<AlertsPlace apiBaseUrl="http://x" bearerToken="t" investigationId="c1" accountId="me" isAdministrator={false} onCanvas={vi.fn()} />);
}

describe("the Monitoring place", () => {
  it("is one place, headed Monitoring, holding the queue, the rules and the watches", async () => {
    serve("viewer");
    place();
    expect(screen.getByRole("heading", { name: "Monitoring" })).toBeTruthy();
    for (const tab of ["Queue", "Rules", "Watches"]) expect(screen.getByRole("tab", { name: tab })).toBeTruthy();
  });

  it("lists every kind with its severity, who may see it and its age", async () => {
    serve("viewer");
    vi.setSystemTime(new Date("2026-11-01T09:00:00Z"));
    place();
    const hotlist = await screen.findByRole("button", { name: alertName("High", "Hotlist", "A hotlisted identifier appeared: 07700 900310") });
    const item = (button: HTMLElement) => within(button.closest("li")!);
    expect(item(hotlist).getByText("High")).toBeTruthy();
    expect(item(hotlist).getByText(/Shared with team unit-a · 2 hours old/)).toBeTruthy();
    const typology = screen.getByRole("button", { name: alertName("Medium", "Structuring") });
    expect(item(typology).getByText(/The case team/)).toBeTruthy();
    const monitor = screen.getByRole("button", { name: alertName("Medium", "Watched pattern") });
    expect(item(monitor).getByText(/Only its owner/)).toBeTruthy();
    expect(screen.getByText("3 alerts you can see.")).toBeTruthy();
    vi.useRealTimers();
  });

  it("filters by kind, severity and status on the server, never by hiding rows here", async () => {
    const calls = serve("viewer");
    place();
    await screen.findByRole("button", { name: alertName("High", "Hotlist") });
    fireEvent.change(screen.getByRole("combobox", { name: "Kind of alert" }), { target: { value: "hotlist" } });
    await waitFor(() => expect(calls).toContain("GET alert-queue?status=active&kind=hotlist"));
    fireEvent.change(screen.getByRole("combobox", { name: "Severity" }), { target: { value: "high" } });
    await waitFor(() => expect(calls).toContain("GET alert-queue?status=active&kind=hotlist&severity=high"));
    fireEvent.change(screen.getByRole("combobox", { name: "Which alerts" }), { target: { value: "closed" } });
    await waitFor(() => expect(calls).toContain("GET alert-queue?status=closed&kind=hotlist&severity=high"));
  });

  it("gives a case alert to a member, by name, and a shared one only to be claimed", async () => {
    const calls = serve("editor", (path, init) =>
      path === "alert-queue/t1/assign" ? json(200, { ...ROWS[1]!.alert, status: "claimed", assignee: JSON.parse(String(init?.body)).assignee }) : null,
    );
    place();
    fireEvent.click(await screen.findByRole("button", { name: alertName("Medium", "Structuring") }));
    const giveTo = await screen.findByRole("combobox", { name: "Give this alert to" });
    expect(within(giveTo).getByRole("option", { name: "Priya Shah" })).toBeTruthy();
    fireEvent.change(giveTo, { target: { value: "member-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Give" }));
    await screen.findByText("Given to Priya Shah.");
    expect(calls).toContain("POST alert-queue/t1/assign");

    fireEvent.click(screen.getByRole("button", { name: alertName("High", "Hotlist") }));
    await screen.findByRole("button", { name: "Claim" });
    expect(screen.queryByRole("combobox", { name: "Give this alert to" })).toBeNull();
    expect(screen.getByText(/claimed by someone who can see it/)).toBeTruthy();
  });

  it("says a hotlist alert's kind, severity and audience when it is opened", async () => {
    serve("viewer");
    place();
    fireEvent.click(await screen.findByRole("button", { name: alertName("High", "Hotlist") }));
    expect(await screen.findByText("Hotlist · High severity · Shared with team unit-a")).toBeTruthy();
    expect(screen.getByRole("list", { name: "What this alert concerns" }).textContent).toContain("07700 900310");
  });

  it("offers the seven typologies and stage (c)'s four AML templates, and one fills the rule form", async () => {
    serve("author");
    place();
    fireEvent.click(screen.getByRole("tab", { name: "Rules" }));
    const list = await screen.findByRole("list", { name: "Templates" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(11);
    expect(TEMPLATES.map((t) => t.typology).sort()).toEqual(
      ["circular_flow", "document_verification", "dormant_reactivated", "high_risk_jurisdiction", "kyc_screening", "large_cash",
       "pattern", "rapid_movement", "shared_attributes", "structuring", "velocity_rise"],
    ); // prettier-ignore
    expect(within(list).getByText(/Raises high-severity alerts/, { selector: "*" })).toBeTruthy();
    fireEvent.click(within(list).getByRole("button", { name: "Use the template: Rapid movement" }));
    expect((screen.getByLabelText("Rule name") as HTMLInputElement).value).toBe("Rapid movement");
    expect((screen.getByRole("combobox", { name: "Typology" }) as HTMLSelectElement).value).toBe("rapid_movement");
    expect((screen.getByLabelText("Leaves within (hours)") as HTMLInputElement).value).toBe("48");
  });

  it("shows templates to a reader who cannot deploy, without the button", async () => {
    serve("viewer");
    place();
    fireEvent.click(screen.getByRole("tab", { name: "Rules" }));
    await screen.findByRole("list", { name: "Templates" });
    expect(screen.queryByRole("button", { name: /Use the template/ })).toBeNull();
  });
});

describe("the age of an alert", () => {
  const now = new Date("2026-11-01T09:00:00Z");
  it("is said in words", () => {
    expect(ageWords("2026-11-01T08:40:00Z", now)).toBe("under an hour old");
    expect(ageWords("2026-11-01T08:00:00Z", now)).toBe("1 hour old");
    expect(ageWords("2026-10-31T08:00:00Z", now)).toBe("1 day old");
    expect(ageWords("2026-10-25T09:00:00Z", now)).toBe("7 days old");
  });
});

describe("a hotlist's audience", () => {
  const hotlist = { id: "h1", identifier: "+447700900310", identifier_typed: "07700 900310", owner_id: "me", review_date: "2027-01-01", status: "active", created_at: "2026-10-26T09:00:00Z", audience: "only_me" };

  function hotlists(editable: boolean, audienceDefault = "only_me", refuse = false) {
    const sent: { method: string; body: unknown; path: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = new URL(url).pathname;
        if (init?.method && init.method !== "GET") sent.push({ method: init.method, body: JSON.parse(String(init.body)), path });
        if (refuse && init?.method === "PUT")
          return json(403, { error: "hotlist_audience_fixed", detail: "This deployment sends every hotlist's alerts to only its owner; the audience cannot be changed here." });
        if (init?.method === "PUT") return json(200, { ...hotlist, audience: "team" });
        if (init?.method === "POST") return json(201, { ...hotlist, id: "h2" });
        return json(200, { hotlists: [hotlist], audience_default: audienceDefault, audience_editable: editable });
      }),
    );
    render(<HotlistPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    return sent;
  }

  it("is chosen for a new hotlist, starting from the deployment's default", async () => {
    const sent = hotlists(true, "team");
    const choice = await screen.findByRole("combobox", { name: "Who its alerts reach" });
    await waitFor(() => expect((choice as HTMLSelectElement).value).toBe("team"));
    fireEvent.change(choice, { target: { value: "only_me" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Identifier" }), { target: { value: "07700 900311" } });
    fireEvent.change(screen.getByLabelText("Review date"), { target: { value: "2027-02-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Add to hotlist" }));
    await waitFor(() => expect(sent[0]?.body).toEqual({ identifier: "07700 900311", review_date: "2027-02-01", audience: "only_me" }));
  });

  it("is changed by its owner on an existing hotlist", async () => {
    const sent = hotlists(true);
    const row = await screen.findByRole("combobox", { name: "Who alerts from 07700 900310 reach" });
    fireEvent.change(row, { target: { value: "team" } });
    await screen.findByText("Alerts from 07700 900310 now reach your team too.");
    expect(sent[0]).toEqual({ method: "PUT", path: "/v1/investigations/inv-1/hotlists/h1/audience", body: { audience: "team" } });
  });

  it("is not offered when the deployment fixes it, and says so", async () => {
    hotlists(false);
    expect(await screen.findByText("07700 900310")).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: /Who/ })).toBeNull();
    expect(screen.getAllByText(/Alerts reach only you\. The deployment sets this\./).length).toBeGreaterThan(0);
  });

  it("says the server's refusal in its own words", async () => {
    hotlists(true, "only_me", true);
    fireEvent.change(await screen.findByRole("combobox", { name: "Who alerts from 07700 900310 reach" }), { target: { value: "team" } });
    expect(await screen.findByText(/the audience cannot be changed here/)).toBeTruthy();
  });
});
