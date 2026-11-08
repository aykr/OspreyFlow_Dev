// @vitest-environment jsdom
// Admin › Audit and Operations' ageing (ADR-145 decisions 9 and 10, L2.6). What each entry may tell is
// the Conduit's (`test_audit_section_routes.py`, `test_audit_section_store.py`); these prove the screen
// sends every filter to it, shows withheld words as withheld and never invents them, says the total,
// and asks for a case before the rule audit.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Audit, entryWords, queryOf } from "./Audit";
import { Ageing } from "./Operations";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const API = { apiBaseUrl: "http://x", bearerToken: "t" };
const ENTRY = {
  recorded_at: "2026-11-08T09:00:00Z", principal_id: "ana-1", principal_name: "Ana Analyst", action: "confirm_node",
  kind: "assertions", held_in: "case_and_admin", investigation_id: "c1", case_name: "Op Kestrel", detail: null,
  words_withheld: true, result_cardinality: null,
} as const; // prettier-ignore
const PEOPLE = { ...ENTRY, action: "set_person_roles", kind: "people_and_roles", investigation_id: null, case_name: null,
                 detail: { user_id: "ana-2", roles: ["analyst"] }, words_withheld: false, result_cardinality: 1 } as const; // prettier-ignore

function serve(answer: (url: URL, init?: RequestInit) => Response) {
  const asked: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = new URL(url);
      asked.push(u);
      return answer(u, init);
    }),
  );
  return asked;
}
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

describe("Admin › Audit", () => {
  it("shows what the Conduit sent, its words withheld where it withheld them, and the total", async () => {
    serve(() => json(200, { entries: [ENTRY, PEOPLE], total: 2, offset: 0, limit: 50, note: "Entries about another unit's cases are not shown." }));
    render(<Audit api={API} />);
    const table = await screen.findByRole("table", { name: "Audit entries" });
    expect(table.textContent).toContain("Ana Analyst");
    expect(table.textContent).toContain("confirm node");
    expect(table.textContent).toContain("Withheld: your own read of this record would not show them");
    expect(table.textContent).toContain("user id: ana-2; roles: [\"analyst\"]");
    expect(screen.getByRole("status").textContent).toBe("Entries 1–2 of 2, newest first.");
    expect(screen.getByText("Entries about another unit's cases are not shown.")).toBeTruthy();
  });

  it("sends every filter to the Conduit and filters nothing itself", async () => {
    const asked = serve(() => json(200, { entries: [ENTRY], total: 1, offset: 0, limit: 50 }));
    render(<Audit api={API} />);
    await screen.findByRole("table", { name: "Audit entries" });
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "assertions" } });
    fireEvent.change(screen.getByLabelText("Person (account id)"), { target: { value: "eng-1" } });
    fireEvent.change(screen.getByLabelText("Case (id)"), { target: { value: "c9" } });
    fireEvent.change(screen.getByLabelText("Dataset (id)"), { target: { value: "ds-b" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-11-08" } });
    fireEvent.click(screen.getByRole("button", { name: "Show entries" }));
    await waitFor(() => expect(asked).toHaveLength(2));
    const q = asked[1]!.searchParams;
    expect(asked[1]!.pathname).toBe("/v1/admin/audit");
    expect(Object.fromEntries(q)).toEqual({
      held_in: "case_and_admin", kind: "assertions", who: "eng-1", case: "c9", dataset: "ds-b",
      since: "2026-11-01T00:00:00.000Z", until: "2026-11-09T00:00:00.000Z", offset: "0", limit: "50",
    }); // prettier-ignore
    // The entry the Conduit sent is shown though it is not eng-1's: the screen narrows nothing.
    expect((await screen.findByRole("table", { name: "Audit entries" })).textContent).toContain("Ana Analyst");
  });

  it("asks for a case before reading the rule audit, then reads it for that case", async () => {
    const asked = serve(() => json(200, { entries: [], total: 0, offset: 0, limit: 50 }));
    render(<Audit api={API} />);
    await waitFor(() => expect(asked).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("Record"), { target: { value: "rules" } });
    expect(screen.queryByLabelText("Kind")).toBeNull();
    expect(screen.queryByLabelText("Dataset (id)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show entries" }));
    expect(screen.getByRole("alert").textContent).toMatch(/^Choose the case whose rule audit to read/);
    expect(asked).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Case (id, required)"), { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Show entries" }));
    await waitFor(() => expect(asked).toHaveLength(2));
    expect(Object.fromEntries(asked[1]!.searchParams)).toMatchObject({ held_in: "rules", case: "c1" });
    expect(await screen.findByText("No entries you may read match these filters.")).toBeTruthy();
  });

  it("says a case it may not read as one not found, and nothing more", async () => {
    serve((u) => (u.searchParams.get("held_in") === "rules" ? json(404, { detail: "not found" }) : json(200, { entries: [], total: 0, offset: 0, limit: 50 })));
    render(<Audit api={API} />);
    fireEvent.change(screen.getByLabelText("Record"), { target: { value: "rules" } });
    fireEvent.change(screen.getByLabelText("Case (id, required)"), { target: { value: "c9" } });
    fireEvent.click(screen.getByRole("button", { name: "Show entries" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "No case of yours by that id: it is not in your unit, or you may not read its rule audit.",
    );
  });

  it("pages by the Conduit's total", async () => {
    const asked = serve((u) => {
      const offset = Number(u.searchParams.get("offset"));
      return json(200, { entries: [ENTRY], total: 120, offset, limit: 50 });
    });
    render(<Audit api={API} />);
    await screen.findByText("Entries 1–1 of 120, newest first.");
    fireEvent.click(screen.getByRole("button", { name: "Older entries" }));
    await screen.findByText("Entries 51–51 of 120, newest first.");
    expect(asked[1]!.searchParams.get("offset")).toBe("50");
  });

  it("reads a date's whole day, and leaves out what a record does not take", () => {
    const q = queryOf({ held_in: "models", kind: "assertions", who: "", case: "c1", dataset: "d", since: "", until: "2026-11-30" }, 0);
    expect(q).toMatchObject({ held_in: "models", kind: undefined, case: undefined, dataset: undefined, until: "2026-12-01T00:00:00.000Z" });
    expect(entryWords({ ...ENTRY, words_withheld: false, detail: {} })).toBe("—");
  });
});

describe("Operations' ageing", () => {
  const AGEING = {
    alert_after_days: 3, promotions_recorded: false, waiting: [],
    rules: [{ what: "A promotion waiting for review", after_days: 3, then: "After 3 days it is flagged overdue." }],
  }; // prettier-ignore

  it("says what ages and when, and that no promotion is recorded yet", async () => {
    serve(() => json(200, AGEING));
    render(<Ageing api={API} />);
    expect(await screen.findByText("After 3 days it is flagged overdue.")).toBeTruthy();
    expect(screen.getByText(/^Promotions from drawing boards are not recorded yet/)).toBeTruthy();
  });

  it("lists each waiting promotion with its age, overdue ones said so", async () => {
    serve(() => json(200, { ...AGEING, promotions_recorded: true, waiting: [
      { promotion_id: "p1", load_id: "load-7", dataset_id: "ds-a", dataset_name: "Prison records", proposed_by: "ana-1",
        proposed_at: "2026-11-01T09:00:00Z", age_days: 4, overdue: true },
    ] })); // prettier-ignore
    render(<Ageing api={API} />);
    const table = await screen.findByRole("table", { name: "Promotions waiting for review" });
    expect(table.textContent).toContain("load-7");
    expect(table.textContent).toContain("4 days, overdue");
  });

  it("saves N days, refusing what the Conduit would", async () => {
    const asked: { method: string; body: unknown }[] = [];
    serve((u, init) => {
      asked.push({ method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
      if (init?.method === "PUT") return json(200, { alert_after_days: 5 });
      return json(200, { ...AGEING, alert_after_days: asked.some((a) => a.method === "PUT") ? 5 : 3 });
    });
    render(<Ageing api={API} />);
    const days = await screen.findByLabelText("Alert the reviewers and administrators after N days");
    fireEvent.change(days, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Save when promotions are overdue" }));
    expect(screen.getByRole("alert").textContent).toBe("The number of days must be a whole number from 1 to 90.");
    fireEvent.change(days, { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save when promotions are overdue" }));
    expect((await screen.findByRole("status")).textContent).toBe("Reviewers and administrators are now alerted after 5 days.");
    expect(asked.find((a) => a.method === "PUT")!.body).toEqual({ alert_after_days: 5 });
  });
});
