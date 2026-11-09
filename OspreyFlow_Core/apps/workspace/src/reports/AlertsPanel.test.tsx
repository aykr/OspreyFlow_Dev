// @vitest-environment jsdom
// The Alerts panel (ADR-146 decision 9): open alerts by source and age, and the newest few. Every
// count is the Conduit's, taken as the reader (rule 7); the newest few only for a reader the queue's
// rows go to; a row opens the alert only for someone Rules and Monitoring is offered to.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MonitoringFigures } from "../../../../packages/schemas/generated";
import { alertRuleGroup, groupName } from "./figureParts";
import { AlertsPanel } from "./AlertsPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const API = { apiBaseUrl: "http://conduit.test", bearerToken: "t", investigationId: "c1" };
const NOW = new Date("2026-11-08T12:00:00Z");

// Synthetic (rule 9): two open by the Conduit's count, as the reader may see them.
export const MONITORING: MonitoringFigures = {
  raised_by_rule: [], closed_by_outcome: [], time_to_close: [], hotlist_matches: [], team: [],
  open_by_source: [
    { label: "typology", typology: "structuring", age: "under a day", count: 1 },
    { label: "hotlists", typology: "", age: "over 30 days", count: 1 },
  ],
};  // prettier-ignore

const row = (id: string, kind: string, status: string, created: string, typology: string | null = null) => ({
  alert: { id, rule_id: `${kind}:r`, owner_id: "o", mode: "full", referent_node_ids: [], created_at: created, status, typology },
  summary: `Alpha Ltd ${id}`,
  kind,
});

// The queue's rows, more than the figures count: the panel must never count them itself.
const ROWS = [
  row("a1", "typology", "open", "2026-11-08T09:00:00Z", "structuring"),
  row("a2", "hotlist", "claimed", "2026-10-01T09:00:00Z"),
  row("a3", "typology", "closed", "2026-11-08T10:00:00Z", "structuring"),
  row("a4", "typology", "open", "2026-11-07T09:00:00Z", "structuring"),
  row("a5", "monitor", "open", "2026-11-06T09:00:00Z"),
];

function serve(queue: () => Response) {
  const asked: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (raw: string) => {
    asked.push(new URL(raw).pathname);
    return queue();
  }));
  return asked;
}
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

describe("the Alerts panel", () => {
  it("counts only what the Conduit counted for the reader, never the rows it was given", async () => {
    serve(() => json(200, ROWS));
    render(<AlertsPanel api={API} monitoring={MONITORING} now={NOW} />);
    await screen.findByRole("list", { name: "Newest alerts" });
    // Four rows are still in the queue, but the Conduit counted two for this reader.
    expect(screen.getByText("2 alerts open")).toBeTruthy();
    const table = screen.getByRole("table", { name: "Open alerts by source and age" });
    expect(within(table).getAllByRole("row").map((r) => r.textContent)).toEqual([
      "SourceUnder a day1 to 7 days7 to 30 daysOver 30 days",
      "Structuring1000",
      "Hotlists0001",
    ]);
  });

  it("lists the newest few still in the queue, newest first, closed ones left out", async () => {
    serve(() => json(200, ROWS));
    render(<AlertsPanel api={API} monitoring={MONITORING} now={NOW} />);
    const list = await screen.findByRole("list", { name: "Newest alerts" });
    const items = within(list).getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual([
      "Structuring: Alpha Ltd a1today",
      "Structuring: Alpha Ltd a41 day old",
      expect.stringMatching(/^Monitors: Alpha Ltd a5/),
      expect.stringMatching(/^Hotlists: Alpha Ltd a2/),
    ]);
  });

  it("shows a reader refused the queue's rows the counts alone, with no alert listed", async () => {
    const asked = serve(() => json(403, { detail: { error: "queue_rows_not_offered" } }));
    render(<AlertsPanel api={API} monitoring={MONITORING} now={NOW} />);
    await waitFor(() => expect(asked).toContain("/v1/investigations/c1/alert-queue"));
    expect(screen.getByText("2 alerts open")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Newest alerts" })).toBeNull();
    expect(screen.queryByText(/could not be read/)).toBeNull();
  });

  it("opens an alert at its address only for a reader Rules and Monitoring is offered to", async () => {
    serve(() => json(200, ROWS));
    const { unmount } = render(<AlertsPanel api={API} monitoring={MONITORING} now={NOW} />);
    const list = await screen.findByRole("list", { name: "Newest alerts" });
    expect(within(list).queryAllByRole("button")).toEqual([]);
    unmount();
    const opened: string[] = [];
    render(<AlertsPanel api={API} monitoring={MONITORING} now={NOW} onOpenAlert={(id) => opened.push(id)} />);
    fireEvent.click(await screen.findByRole("button", { name: "Structuring: Alpha Ltd a1" }));
    expect(opened).toEqual(["a1"]);
  });

  it("shows only the rule group it is filtered to, and is outlined when an alert opened it", async () => {
    serve(() => json(200, ROWS));
    render(<AlertsPanel api={API} monitoring={MONITORING} now={NOW} only={{ label: "hotlists", typology: "" }} outlined />);
    const list = await screen.findByRole("list", { name: "Newest alerts" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("1 alert open")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Alerts" }).getAttribute("data-outlined")).toBe("true");
  });
});

describe("the newest few under a filter", () => {
  it("are the group's own newest, even when more than a few newer alerts of other groups come first", async () => {
    // Six typology alerts newer than the one hotlist alert: cut before the filter, the hotlist row is lost.
    const newer = Array.from({ length: 6 }, (_, i) =>
      row(`t${i}`, "typology", "open", `2026-11-08T1${i}:00:00Z`, "structuring"),
    );
    serve(() => json(200, [...newer, row("h-old", "hotlist", "open", "2026-11-01T09:00:00Z")]));
    render(<AlertsPanel api={API} monitoring={MONITORING} now={NOW} only={{ label: "hotlists", typology: "" }} />);
    const list = await screen.findByRole("list", { name: "Newest alerts" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      expect.stringMatching(/^Hotlists: Alpha Ltd h-old/),
    ]);
  });
});

describe("a rule group's name", () => {
  it("is its own for every kind, so L2.10's analyst alerts and any later kind never read as one another or as a typology", () => {
    const names = [
      groupName({ label: "typology", typology: "structuring" }),
      groupName({ label: "typology", typology: "" }),
      groupName({ label: "hotlists", typology: "" }),
      groupName({ label: "monitors", typology: "" }),
      groupName({ label: "analyst", typology: "" }),
      groupName({ label: "watch", typology: "" }),
    ];
    expect(new Set(names).size).toBe(names.length);
    expect(groupName(alertRuleGroup({ kind: "analyst", alert: {} }))).toBe("Raised by an analyst");
    expect(groupName({ label: "watch", typology: "" })).toBe("Watch");
  });
});
