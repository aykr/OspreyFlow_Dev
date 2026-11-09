// @vitest-environment jsdom
// The Alert monitoring board (ADR-145 Amendment 4 decision 9, D2): first on the Glass's Dashboards,
// drawn by the Glass from the figures the Conduit counted for the reader (rules 3 and 7), asking
// Superset for nothing; filtered to a rule group and a period, as *See the trend* and the Reports
// Viewer's *Open the dashboard* open it.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ALERT_MONITORING, AlertMonitoringBoard } from "./AlertMonitoringBoard";
import { EmbeddedDashboards, type Embed } from "./EmbeddedDashboards";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const API = { apiBaseUrl: "http://api", bearerToken: "t", investigationId: "c1" };
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

// Synthetic (rule 9).
const FIGURES = {
  period_weeks: 12, as_of: "2026-11-08", generated_at: "2026-11-08T08:00:00Z", alerts_total: 3,
  alerts_by_week: [], open_by_age: [], outcomes: [],
  monitoring: {
    raised_by_rule: [
      { week_start: "2026-10-26", label: "typology", typology: "structuring", count: 2 },
      { week_start: "2026-11-02", label: "typology", typology: "structuring", count: 1 },
      { week_start: "2026-11-02", label: "hotlists", typology: "", count: 4 },
    ],
    closed_by_outcome: [{ week_start: "2026-11-02", label: "false_positive", typology: "", count: 3 }],
    time_to_close: [{ label: "under a day", value: 2 }, { label: "1 to 7 days", value: 1 }],
    hotlist_matches: [{ week_start: "2026-11-02", label: "hotlists", typology: "", count: 4 }],
    open_by_source: [
      { label: "typology", typology: "structuring", age: "under a day", count: 1 },
      { label: "hotlists", typology: "", age: "1 to 7 days", count: 2 },
    ],
    team: [
      { label: "typology", typology: "structuring", unassigned: 1, mine: 0, older_than_week: 0, closed: 2, not_of_interest: 1 },
      { label: "hotlists", typology: "", unassigned: 0, mine: 2, older_than_week: 1, closed: 1, not_of_interest: 0 },
    ],
  },
};  // prettier-ignore

function serve() {
  const asked: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (raw: string, init?: RequestInit) => {
    const url = new URL(raw);
    asked.push(`${init?.method ?? "GET"} ${url.pathname}${url.search}`);
    if (url.pathname === "/v1/reports/dashboards") return json(200, [{ slug: "fraud-board", title: "Fraud board" }]);
    if (url.pathname.endsWith("/guest-token")) return json(200, { token: "g", uuid: "uuid-fraud", superset_origin: "http://bi.example" });
    if (url.pathname.endsWith("/alert-queue")) return json(200, []);
    return json(200, FIGURES);
  }));
  return asked;
}

const rows = (name: string) =>
  within(screen.getByRole("list", { name })).getAllByRole("listitem").map((li) => li.textContent);

describe("the Alert monitoring board", () => {
  it("is the first board on the Dashboards, drawn by the Glass with no Superset token asked for it", async () => {
    const asked = serve();
    const embed = vi.fn<Embed>(async () => ({}));
    render(<EmbeddedDashboards apiBaseUrl="http://api" bearerToken="t" embed={embed}
                               leading={{ ...ALERT_MONITORING, draw: () => <AlertMonitoringBoard api={API} /> }} />);  // prettier-ignore
    const chooser = await screen.findByRole("group", { name: "Choose a dashboard" });
    expect(within(chooser).getAllByRole("button").map((b) => b.textContent)).toEqual(["Alert monitoring", "Fraud board"]);
    await screen.findByRole("list", { name: "Raised by rule" });
    expect(document.querySelector(".embedded-dashboard")).toBeNull();
    expect(asked.some((a) => a.includes("guest-token"))).toBe(false);
    expect(embed).not.toHaveBeenCalled();
    fireEvent.click(within(chooser).getByRole("button", { name: "Fraud board" }));
    await waitFor(() => expect(embed).toHaveBeenCalledOnce());
    expect(screen.queryByRole("region", { name: "Alert monitoring" })).toBeNull();
  });

  it("draws every section from the Conduit's figures for every rule", async () => {
    serve();
    render(<AlertMonitoringBoard api={API} />);
    await screen.findByRole("list", { name: "Raised by rule" });
    expect(rows("Raised by rule")).toEqual(["Structuring: 3", "Hotlists: 4"]);
    expect(rows("Raised each week")).toEqual(["Week of 2026-10-26: 2", "Week of 2026-11-02: 5"]);
    expect(rows("Closed by outcome")).toEqual(["False positive: 3"]);
    expect(rows("Time to close")).toEqual(["under a day: 2", "1 to 7 days: 1"]);
    expect(screen.getByRole("region", { name: "Hotlist matches" }).textContent).toContain("4 matches");
    const team = screen.getByRole("table", { name: "Team view by rule" });
    expect(within(team).getAllByRole("row").slice(1).map((r) => r.textContent)).toEqual([
      "Structuring10050% of 2", "Hotlists0210% of 1"]);  // prettier-ignore
  });

  it("opens filtered to an alert's rule and period, and every figure follows the filter", async () => {
    const asked = serve();
    render(<AlertMonitoringBoard api={API} filter={{ rule: { label: "typology", typology: "structuring" }, weeks: 4 }} />);
    await screen.findByRole("list", { name: "Raised by rule" });
    expect(asked).toContain("GET /v1/investigations/c1/reports?weeks=4");
    expect((screen.getByRole("combobox", { name: "Rule" }) as HTMLSelectElement).value).toBe("typology:structuring");
    expect(rows("Raised by rule")).toEqual(["Structuring: 3"]);
    expect(rows("Raised each week")).toEqual(["Week of 2026-10-26: 2", "Week of 2026-11-02: 1"]);
    expect(screen.getByRole("region", { name: "Alerts" }).textContent).toContain("1 alert open");
    expect(screen.queryByRole("region", { name: "Hotlist matches" })).toBeNull();
    expect(screen.getByRole("region", { name: "Closed by outcome (every rule)" })).toBeTruthy();
    const team = screen.getByRole("table", { name: "Team view by rule" });
    expect(within(team).getAllByRole("row").slice(1).map((r) => r.textContent)).toEqual(["Structuring10050% of 2"]);
    fireEvent.change(screen.getByRole("combobox", { name: "Rule" }), { target: { value: "" } });
    expect(rows("Raised by rule")).toEqual(["Structuring: 3", "Hotlists: 4"]);
  });

  it("opened from an alert, says so and goes back", async () => {
    serve();
    const back = vi.fn();
    render(<AlertMonitoringBoard api={API} fromAlert={{ words: "the structuring alert", onBack: back }} />);
    const note = await screen.findByRole("note", { name: "Opened from an alert" });
    expect(document.activeElement).toBe(within(note).getByRole("button", { name: "← Back to your alerts" }));
    fireEvent.click(within(note).getByRole("button", { name: "← Back to your alerts" }));
    expect(back).toHaveBeenCalledOnce();
  });

  it("keeps the reader's focus when its parent draws again with an equal way back (WCAG 2.4.3)", async () => {
    serve();
    const board = (onBack: () => void) => (
      <AlertMonitoringBoard api={API} fromAlert={{ words: "the structuring alert", onBack }} />);
    const { rerender } = render(board(vi.fn()));
    await screen.findByRole("note", { name: "Opened from an alert" });
    const rule = screen.getByRole("combobox", { name: "Rule" });
    rule.focus();
    rerender(board(vi.fn()));  // App builds the way back afresh on every render
    expect(document.activeElement).toBe(rule);
  });
});

describe("a Superset board under the Glass's own board's slug", () => {
  it("is left out, never shadowing the Alert monitoring board or listed twice", async () => {
    vi.stubGlobal("fetch", vi.fn(async (raw: string) => {
      const url = new URL(raw);
      if (url.pathname === "/v1/reports/dashboards")
        return json(200, [{ slug: "alert-monitoring", title: "Someone's board" }, { slug: "fraud-board", title: "Fraud board" }]);
      if (url.pathname.endsWith("/alert-queue")) return json(200, []);
      return json(200, FIGURES);
    }));  // prettier-ignore
    render(<EmbeddedDashboards apiBaseUrl="http://api" bearerToken="t" embed={vi.fn<Embed>(async () => ({}))}
                               leading={{ ...ALERT_MONITORING, draw: () => <AlertMonitoringBoard api={API} /> }} />);  // prettier-ignore
    const chooser = await screen.findByRole("group", { name: "Choose a dashboard" });
    await waitFor(() => expect(within(chooser).getAllByRole("button")).toHaveLength(2));
    expect(within(chooser).getAllByRole("button").map((b) => b.textContent)).toEqual(["Alert monitoring", "Fraud board"]);
  });
});
