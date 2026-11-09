// @vitest-environment jsdom
// ADR-140 Amendment 13 (phase 9 and the screening-list connector), the Glass. What would fail if each
// part were wrong: a source on a SQL connection registered with a file instead of its read, or a read
// holding a field the Conduit would refuse; a subscription sent by the list's name instead of its id; a
// blank list sent without its column picks, or a format's template sent with some; the manage actions
// shown to someone who may not load screening lists.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DeploymentList, SubscribableList } from "../../../../../packages/schemas/generated";
import { fileNameOf, readOf, RegisterSourceWizard } from "./RegisterSourceWizard";
import { ImportListForm, ScreeningLists } from "./ScreeningLists";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const API = { apiBaseUrl: "http://api", bearerToken: "t" };
const SCHEME = { name: "uk", classification: ["OFFICIAL"], handling_codes: { P: { label: "Permitted", dissemination: "permitted" as const } } };
const LIST: DeploymentList = {
  id: "01LISTID", name: "Client list", template: "blank", location: "client.csv", synthetic: true,
  licence: "the client's own list", version: 2, entries: 3, schedule_words: null, created_by: "eng-1",
  created_at: "2026-11-08T09:00:00Z", updated_at: "2026-11-08T09:05:00Z",
};  // prettier-ignore

const SUB: SubscribableList = { id: "01LISTID", name: "Client list", template: "blank", version: 2, entries: 3,
  updated_at: "2026-11-08T09:05:00Z", failing: false, schedule_words: null };  // prettier-ignore

type Call = { path: string; method: string; body: unknown };
function serve(routes: Record<string, unknown>, statuses: Record<string, number> = {}): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      const method = init?.method ?? "GET";
      calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : null });
      const key = `${method} ${path}`;
      const status = statuses[key] ?? (key in routes ? 200 : 404);
      return { ok: status === 200, status, json: async () => routes[key] ?? {} } as Response;
    }),
  );
  return calls;
}

describe("a source's read", () => {
  it("names its file in the Conduit's own characters", () => {
    expect(fileNameOf("Visit bookings (NOMIS)")).toBe("visit_bookings_nomis");
    expect(fileNameOf("  --x--  ")).toBe("x");
  });

  it("is built from the fields its connection's kind takes, or not at all", () => {
    const f = { table: "nomis.visit_bookings", columns: "booking_id, prisoner,", path: "", recordsAt: "", pattern: "" };
    expect(readOf("sql", f)).toEqual({ kind: "sql", table: "nomis.visit_bookings", columns: ["booking_id", "prisoner"] });
    expect(readOf("api", f)).toBeNull();
    expect(readOf("api", { ...f, path: "/v1/n", recordsAt: "data.items" })).toEqual({ kind: "api", path: "/v1/n", records_at: "data.items" });
    expect(readOf("json", { ...f, pattern: "b-*.json" })).toEqual({ kind: "json", pattern: "b-*.json", records_at: null });
  });

  it("registers a SQL source by its read, never a file", async () => {
    const calls = serve({
      "GET /v1/ingest/connections": [
        { id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "" },
        { id: "c-sql", kind: "sql", name: "NOMIS replica", created_by: "adm", created_at: "" },
      ],
      "GET /v1/datasets/ds-a/source-files": { root: "/in", files: [] },
      "POST /v1/datasets/ds-a/sources": { id: "s1" },
    });
    render(<RegisterSourceWizard api={API} datasetId="ds-a" scheme={SCHEME} registered={[]} onRegistered={() => undefined} onCancel={() => undefined} />);
    await waitFor(() => expect(screen.getByRole("option", { name: "NOMIS replica" })).toBeTruthy());
    fireEvent.change(screen.getByRole("combobox", { name: "Connection" }), { target: { value: "c-sql" } });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("What to read")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Source name" }), { target: { value: "Visit bookings" } });
    expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "Table or view (schema.name)" }), { target: { value: "nomis.visit_bookings" } });
    expect(screen.getByText("Each read lands as visit_bookings.csv in the dataset's folder.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("button", { name: "Register" })).toBeTruthy();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});

describe("the screening lists", () => {
  it("subscribes by the list's id and shows Manage only to whoever may load lists", async () => {
    const calls = serve(
      {
        "GET /v1/datasets/ds-a/screening-subscriptions": { lists: [SUB], subscribed: [] },
        "GET /v1/datasets/ds-a/reference-lists/offered": [],
        "PUT /v1/datasets/ds-a/screening-subscriptions/01LISTID": { lists: [SUB], subscribed: ["01LISTID"] },
      },
      { "GET /v1/studio/screening-lists": 403 },
    );
    render(<ScreeningLists api={API} datasetId="ds-a" />);
    const box = await screen.findByRole("checkbox", { name: "Subscribe this dataset to Client list" });
    expect(screen.queryByRole("button", { name: "Refresh now: Client list" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Import a list" })).toBeNull();
    fireEvent.click(box);
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("This dataset now reads Client list."));
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.path).toBe("/v1/datasets/ds-a/screening-subscriptions/01LISTID");
  });

  it("refreshes a list now for whoever may load lists, saying what the import did", async () => {
    serve({
      "GET /v1/datasets/ds-a/screening-subscriptions": { lists: [SUB], subscribed: ["01LISTID"] },
      "GET /v1/datasets/ds-a/reference-lists/offered": [{ id: "01LISTID", name: "Client list", kind: "screening", version: 2, deployment_wide: true }],
      "GET /v1/studio/screening-lists": [LIST],
      "POST /v1/studio/screening-lists/01LISTID/refresh": { list_id: "01LISTID", outcome: "unchanged", words: "Client list is unchanged at version 2" },
    });
    render(<ScreeningLists api={API} datasetId="ds-a" />);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh now: Client list" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Client list is unchanged at version 2"));
    const read = screen.getByRole("list", { name: "Lists this dataset reads" });
    expect(within(read).getByText("Client list, version 2 (deployment-wide, subscribed)")).toBeTruthy();
  });

  it("sends a blank list's column picks, and a format's template without any", () => {
    const sent: unknown[] = [];
    render(<ImportListForm onCancel={() => undefined} onSubmit={(b) => sent.push(b)} />);
    fireEvent.change(screen.getByRole("textbox", { name: "List name" }), { target: { value: "OFAC" } });
    fireEvent.change(screen.getByRole("textbox", { name: "File in the ingest folder" }), { target: { value: "lists/SDN.CSV" } });
    fireEvent.click(screen.getByRole("button", { name: "Add and import" }));
    expect(sent[0]).toEqual({ name: "OFAC", template: "ofac_sdn", location: "lists/SDN.CSV", mapping: null });
    fireEvent.change(screen.getByRole("combobox", { name: "Template" }), { target: { value: "blank" } });
    expect(screen.getByRole("button", { name: "Add and import" }).hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "Reference column" }), { target: { value: "Client ref" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Name column" }), { target: { value: "Full name" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Aliases column (optional)" }), { target: { value: "Other names" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Many values in one cell are separated by" }), { target: { value: "," } });
    fireEvent.click(screen.getByRole("button", { name: "Add and import" }));
    expect(sent[1]).toEqual({
      name: "OFAC", template: "blank", location: "lists/SDN.CSV",
      mapping: { ref: "Client ref", primary_name: "Full name", aliases: "Other names", date_of_birth: null,
                 nationality: null, identifiers: null, programme: null, separator: ",", entity_type: "Person",
                 entity_type_column: null, listing: "sanction" },
    });  // prettier-ignore
  });
});
