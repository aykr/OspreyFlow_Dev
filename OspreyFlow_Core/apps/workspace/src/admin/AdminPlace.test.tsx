// @vitest-environment jsdom
// ADR-110 Amendment 1, ADR-112: the Admin area. Tabs follow the account's rights; a person's roles are
// saved whole with their other grants kept; a dashboard's secret is shown once; a refusal is said.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace, feedFreshness } from "./AdminPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const PERSON = { id: "u1", username: "osprey-demo-analyst", name: "Demo Analyst", enabled: true,
                 roles: ["analyst", "right:read_export_ledger"], clearance: "OFFICIAL", org_unit: "verify" };  // prettier-ignore

function serve(handler: (path: string, init?: RequestInit) => Response | null = () => null) {
  const sent: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      sent.push({ path: `${init?.method ?? "GET"} ${path}`, body: init?.body ? JSON.parse(String(init.body)) : null });
      const answered = handler(path, init);
      if (answered) return answered;
      if (path === "people") return json(200, [PERSON]);
      if (path === "people/u1/roles") return json(200, { ...PERSON, roles: (JSON.parse(String(init?.body)) as { roles: string[] }).roles });
      if (path === "dashboards" && init?.method === "POST")
        return json(201, { dashboard: { client_id: "osprey-dashboard-board", account_id: "sa-1", clearance: "OFFICIAL", org_unit: "verify" }, secret: "s3cret" });
      if (path === "dashboards") return json(200, []);
      if (path === "/v1/handling-scheme") return json(200, { classification: ["OFFICIAL", "SECRET"] });
      if (path === "system") return json(200, { version: "1.2", components: [{ name: "Graph store", ok: false, millis: 5000, detail: "unreachable" }] });
      return json(404, {});
    }),
  );
  return sent;
}

function place(rights: string[]) {
  render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);
}

describe("the Admin area", () => {
  it("shows only the tabs the account holds a right for", async () => {
    serve();
    place(["administer_system"]);
    expect(screen.queryByRole("tab", { name: "People and roles" })).toBeNull();
    expect(await screen.findByText("not answering: unreachable")).toBeTruthy();
  });

  it("saves a person's roles whole, keeping their other grants", async () => {
    const sent = serve();
    place(["manage_people"]);
    fireEvent.click(await screen.findByLabelText("Reports Viewer for osprey-demo-analyst"));
    fireEvent.click(screen.getByRole("button", { name: "Save roles for osprey-demo-analyst" }));
    await waitFor(() => expect(sent.some((s) => s.path === "PUT people/u1/roles")).toBe(true));
    expect(sent.find((s) => s.path === "PUT people/u1/roles")?.body).toEqual({
      roles: ["analyst", "reports_viewer", "right:read_export_ledger"],
    });
    expect(await screen.findByText(/Saved\./)).toBeTruthy();
  });

  it("registers a dashboard and shows its secret once", async () => {
    serve();
    place(["manage_dashboards"]);
    fireEvent.change(await screen.findByLabelText("Dashboard name"), { target: { value: "Board" } });
    fireEvent.change(screen.getByLabelText("Dashboard unit"), { target: { value: "verify" } });
    await waitFor(() => expect((screen.getByLabelText("Dashboard clearance") as HTMLSelectElement).value).toBe("OFFICIAL"));
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(await screen.findByText("s3cret")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Dashboard identities" }).textContent).toContain("sa-1");
  });

  it("says why a dashboard above one's clearance is refused", async () => {
    serve((path, init) =>
      path === "dashboards" && init?.method === "POST"
        ? json(403, { detail: { error: "dashboard_above_your_clearance", clearance: "SECRET" } })
        : null,
    );
    place(["manage_dashboards"]);
    fireEvent.change(await screen.findByLabelText("Dashboard name"), { target: { value: "Board" } });
    fireEvent.change(screen.getByLabelText("Dashboard unit"), { target: { value: "verify" } });
    await waitFor(() => expect((screen.getByLabelText("Dashboard clearance") as HTMLSelectElement).value).toBe("OFFICIAL"));
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(await screen.findByText("A dashboard cannot read above your own clearance (SECRET asked).")).toBeTruthy();
  });
});

describe("how fresh a dashboard's figures are", () => {
  const base = { client_id: "osprey-dashboard-board", account_id: "sa-1" };

  it("says a standing failure first, in the sync service's words, with the last good pull", () => {
    const shown = feedFreshness({ ...base, last_pulled: "2026-10-11T10:24:32Z", last_failure: "the feed was refused (403)",
                                  failed_at: "2026-10-11T10:39:00Z", cases_pulled: 1 });  // prettier-ignore
    expect(shown).toEqual({
      text: "Failing since 2026-10-11 10:39 UTC: the feed was refused (403); last good pull 2026-10-11 10:24 UTC",
      failing: true,
    });
  });

  it("says when it last pulled, and how many cases", () => {
    expect(feedFreshness({ ...base, last_pulled: "2026-10-11T10:24:32Z", cases_pulled: 2 })).toEqual({
      text: "Pulled 2026-10-11 10:24 UTC · 2 cases",
      failing: false,
    });
  });

  it("says a dashboard never pulled has been given no case", () => {
    expect(feedFreshness(base).text).toBe("Never pulled: no case has given it Viewer yet");
  });
});
