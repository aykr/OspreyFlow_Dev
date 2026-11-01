// @vitest-environment jsdom
// ADR-133 stage (c): the Monitoring place's Lists tab. Each list's version, entries, last update and
// state — a failure in words — with its licence; whoever may load lists refreshes one, subscribes
// to one and reads the refreshes; anyone else reads the lists from the route that carries no
// deployment-wide counts (rule 7), and is offered no action. The data is synthetic (rule 9).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ListsPanel, listState } from "./ListsPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

const LISTS = [
  {
    list_name: "Synthetic list", source: "opensanctions", location: "lists/synthetic_opensanctions_v2.ftm.json",
    dataset: null, synthetic: true, licence: "CC BY-NC 4.0: non-commercial use only, unless licensed by OpenSanctions",
    licence_confirmed: false,
    licence_note: "OpenSanctions is CC BY-NC 4.0, and screening in a business is commercial use, which needs OpenSanctions' own data licence",
    version: "sha256:3906852638793da1", entries: 10, updated_at: "2026-11-01T09:00:00Z",
    attempted_at: "2026-11-01T09:00:00Z", failure: null,
  },
  {
    list_name: "OFAC SDN", source: "ofac_sdn", location: "lists/SDN.CSV", dataset: "ofac_sdn", synthetic: false,
    licence: "US Government work, in the public domain (17 U.S.C. §105)", licence_confirmed: true, licence_note: null,
    version: null, entries: 0,
    updated_at: null, attempted_at: "2026-11-01T09:05:00Z",
    failure: "Refused: “ofac_sdn” is real data and is not in this device's real_data_exceptions.yaml for local development; nothing was loaded (rule 9).",
  },
]; // prettier-ignore

const UPDATE = {
  id: "u1", list_name: "Synthetic list", at: "2026-11-01T09:00:00Z", outcome: "updated", version: "sha256:3906852638793da1",
  previous_version: "sha256:f0c7091a6a53d6a2", added: 1, changed: 1, delisted: 1, rescreened: 4, alerts: 1,
  words: "Version sha256:3906852638793da1: 1 added, 1 changed, 1 removed. 4 customers re-screened against 2 changed entries; 1 alert raised.",
}; // prettier-ignore

function serve() {
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      const method = init?.method ?? "GET";
      calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (path === "/v1/screening-lists") return json(200, { lists: LISTS, can_manage: false });
      if (path === "/v1/admin/screening-lists" && method === "GET")
        return json(200, { lists: LISTS, updates: [UPDATE], can_manage: true });
      if (path === "/v1/admin/screening-lists" && method === "POST")
        return json(201, { ...LISTS[1], list_name: "UN list", source: "un_consolidated", failure: null, attempted_at: null });
      if (path === "/v1/admin/screening-lists/Synthetic%20list/refresh") return json(200, UPDATE);
      if (path === "/v1/admin/screening-lists/OFAC%20SDN/refresh")
        return json(200, { ...UPDATE, list_name: "OFAC SDN", outcome: "refused", words: LISTS[1]!.failure });
      return json(404, {});
    }),
  );
  return calls;
}

const props = { apiBaseUrl: "http://api.invalid", bearerToken: "t" };

describe("the Lists tab", () => {
  it("marks a list whose licence is not confirmed, with the reason in words, and no other", async () => {
    // The owner's answer of 1 November 2026 (ADR-133 Amendment 3): UN and OpenSanctions.
    serve();
    render(<ListsPanel {...props} canManage={false} />);
    const table = await screen.findByRole("table", { name: "Screening lists and their versions" });
    const [, synthetic, ofac] = within(table).getAllByRole("row");
    expect(synthetic!.textContent).toContain(
      "Licence not confirmed: OpenSanctions is CC BY-NC 4.0, and screening in a business is commercial use, which needs OpenSanctions' own data licence. Synthetic lists only.",
    );
    expect(ofac!.textContent).not.toContain("Licence not confirmed");
  });

  it("says in the subscribe form which connectors' licences are not confirmed, and why", async () => {
    serve();
    render(<ListsPanel {...props} canManage={true} />);
    const connector = (await screen.findByRole("combobox", { name: "Connector" })) as HTMLSelectElement;
    const labels = Array.from(connector.options).map((o) => o.textContent);
    expect(labels).toContain("UN Security Council consolidated list (licence not confirmed)");
    expect(labels).toContain("OpenSanctions (FollowTheMoney entities) (licence not confirmed)");
    expect(labels).toContain("OFAC SDN list (US Treasury)");
    fireEvent.change(connector, { target: { value: "un_consolidated" } });
    const form = screen.getByRole("form", { name: "Subscribe to a list" });
    expect(form.textContent).toContain(
      "Licence not confirmed: no open licence was found for the UN consolidated list, and the UN's general terms allow personal, non-commercial use only; its terms are to be confirmed with the UN. Only OspreyFlow's synthetic list may be read through this connector.",
    );
    fireEvent.change(connector, { target: { value: "ofac_sdn" } });
    expect(form.textContent).not.toContain("Licence not confirmed");
  });


  it("shows each list's version, entries, last update, licence and state in words", async () => {
    serve();
    render(<ListsPanel {...props} canManage={false} />);
    const table = await screen.findByRole("table", { name: "Screening lists and their versions" });
    const rows = within(table).getAllByRole("row");
    const synthetic = rows[1]!;
    const ofac = rows[2]!;
    expect(synthetic.textContent).toContain("sha256:3906852638793da1");
    expect(synthetic.textContent).toContain("10");
    expect(synthetic.textContent).toContain("1 Nov 2026");
    expect(synthetic.textContent).toContain("OpenSanctions (FollowTheMoney entities) · synthetic");
    expect(synthetic.textContent).toContain("Licence: CC BY-NC 4.0");
    expect(synthetic.textContent).toContain("Up to date with its last refresh.");
    expect(ofac.textContent).toContain("is real data and is not in this device's real_data_exceptions.yaml");
    expect(ofac.textContent).toContain("real data (ofac_sdn)");
  });

  it("reads a reader's lists from the route without counts, and offers no action", async () => {
    const calls = serve();
    render(<ListsPanel {...props} canManage={false} />);
    await screen.findByRole("table", { name: "Screening lists and their versions" });
    expect(calls.map((c) => c.path)).toEqual(["/v1/screening-lists"]);
    expect(screen.queryByRole("button", { name: /Refresh now/ })).toBeNull();
    expect(screen.queryByRole("form", { name: "Subscribe to a list" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Latest refreshes" })).toBeNull();
    expect(screen.getByText("An administrator or a data engineer subscribes to a list and refreshes it.")).toBeTruthy();
  });

  it("refreshes a list for whoever may load lists, and says what the refresh did", async () => {
    const calls = serve();
    render(<ListsPanel {...props} canManage />);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh now: Synthetic list" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("1 alert raised"));
    expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/Synthetic%20list/refresh"))).toBe(true);
    const refreshes = screen.getByRole("region", { name: "Latest refreshes" });
    expect(refreshes.textContent).toContain("4 customers re-screened against 2 changed entries");
  });

  it("subscribes to a list through its connector and a file in the ingest folder", async () => {
    const calls = serve();
    render(<ListsPanel {...props} canManage />);
    const form = await screen.findByRole("form", { name: "Subscribe to a list" });
    fireEvent.change(within(form).getByLabelText("List name"), { target: { value: "UN list" } });
    fireEvent.change(within(form).getByLabelText("Connector"), { target: { value: "un_consolidated" } });
    fireEvent.change(within(form).getByLabelText("File in the ingest folder"), { target: { value: "lists/consolidated.xml" } });
    fireEvent.change(within(form).getByLabelText("Real dataset"), { target: { value: "un_consolidated" } });
    fireEvent.click(within(form).getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Subscribed to “UN list”"));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      list_name: "UN list", source: "un_consolidated", location: "lists/consolidated.xml",
      dataset: "un_consolidated", use: "local_development",
    }); // prettier-ignore
  });

  it("says a list never read, failing or current", () => {
    expect(listState({ ...LISTS[0], version: null } as never)).toBe("Not yet read: refresh it to load its first version.");
    expect(listState(LISTS[1] as never)).toContain("Refused:");
  });
});
