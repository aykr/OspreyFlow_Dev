// @vitest-environment jsdom
// L2.5 (ADR-145 decisions 6 and 7 and Amendment 5): Admin › People's row (roles, the Super user preset,
// custom roles, the places they open, case levels), *Name an Author*, *Disable…* with transfers, and
// Admin › Roles. The Glass never refuses in the Conduit's stead: each refusal shown is the Conduit's.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "./AdminPlace";
import { groupsFor, RIGHT_GROUPS } from "./sections/Roles";
import { levelWords } from "./sections/People";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const ANA = { id: "u1", username: "ana", name: "Ana Analyst", enabled: true, roles: ["analyst", "role:r1"],
              clearance: "OFFICIAL", org_unit: "verify" };  // prettier-ignore
const BEA = { ...ANA, id: "u2", username: "bea", name: "Bea Engineer", roles: ["data_engineer"] };
const CATALOGUE = {
  built_in: [
    { id: "analyst", label: "Analyst", rights: ["investigate", "triage_alerts"], gives: [] },
    { id: "data_engineer", label: "Data Engineer", rights: ["edit_pipelines", "review_promotions"], gives: [] },
    { id: "super_user", label: "Super user", rights: ["investigate"], gives: ["analyst", "data_engineer", "rule_author"] },
  ],
  custom: [{ id: "r1", name: "Intel desk", version: 2, rights: ["investigate"], changed_by: "a", changed_at: "", holders: 1,
             team: { role_id: "r1", display_name: "Intel", mailbox: "intel@example.org", lead: "u1", cover: null,
                     cover_until: null, acting_lead: "u1", members: [{ id: "u1", name: "Ana Analyst" }] } }],
};  // prettier-ignore
const ROWS = {
  rows: [{ id: "u1", levels: [{ investigation_id: "c1", name: "Kestrel", level: "author", through: null },
                              { investigation_id: "c2", name: "Heron", level: "editor", through: "Intel" }] }],
  without_author: [{ investigation_id: "c3", name: "Wren" }],
};  // prettier-ignore

function serve(handler: (path: string, init?: RequestInit) => Response | null = () => null) {
  const sent: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      sent.push({ path: `${init?.method ?? "GET"} ${path}`, body: init?.body ? JSON.parse(String(init.body)) : null });
      const answered = handler(path, init);
      if (answered) return answered;
      if (path === "people") return json(200, [ANA, BEA]);
      if (path === "people/rows") return json(200, ROWS);
      if (path === "roles") return json(200, CATALOGUE);
      if (path === "organisation-arrivals") return json(200, []);
      if (path.endsWith("/roles")) return json(200, { ...ANA, roles: (JSON.parse(String(init?.body)) as { roles: string[] }).roles });
      return json(200, {});
    }),
  );
  return sent;
}

const place = (rights: string[]) => render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);

describe("Admin › People's row (R3)", () => {
  it("says each person's places and case levels, a team's level through the team", async () => {
    serve();
    place(["manage_people"]);
    expect(await screen.findByText("Author of Kestrel; Editor of Heron through Intel")).toBeTruthy();
    expect(await screen.findAllByText(/^Opens /)).toBeTruthy();
    expect(levelWords([])).toBe("No case levels");
  });

  it("gives the Super user preset as its three roles, and keeps a custom role", async () => {
    const sent = serve();
    place(["manage_people"]);
    await screen.findByText("Author of Kestrel; Editor of Heron through Intel");
    expect((screen.getByRole("checkbox", { name: "Intel desk for ana" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Super user preset for ana" }));
    fireEvent.click(screen.getByRole("button", { name: "Save roles for ana" }));
    await waitFor(() => expect(sent.some((s) => s.path === "PUT people/u1/roles")).toBe(true));
    const body = sent.find((s) => s.path === "PUT people/u1/roles")?.body as { roles: string[] };
    expect([...body.roles].sort()).toEqual(["analyst", "data_engineer", "role:r1", "rule_author"]);
  });
});

describe("Admin › People's cases with no Author (R1)", () => {
  it("names an Author through Admin's own route", async () => {
    const sent = serve();
    place(["manage_people"]);
    const note = await screen.findByRole("note", { name: "Cases with no Author" });
    fireEvent.change(within(note).getByRole("combobox", { name: "Author for Wren" }), { target: { value: "u2" } });
    fireEvent.click(within(note).getByRole("button", { name: "Name an Author of Wren" }));
    await waitFor(() => expect(sent.some((s) => s.path === "PUT cases/c3/authors/u2")).toBe(true));
  });
});

describe("Admin › People's Disable… (A4)", () => {
  const PLAN = { person: "u1", not_yet_listed: ["boards", "proposed types"],
                 items: [{ kind: "case_author", id: "c1", label: "Only Author of the case Kestrel" },
                         { kind: "team_lead", id: "r1", label: "Lead of the team Intel" }] };  // prettier-ignore

  it("lists what they own and shows the Conduit's refusal while an item is untransferred", async () => {
    const sent = serve((path) => {
      if (path === "people/u1/disable-plan") return json(200, PLAN);
      if (path === "people/u1/disable")
        return json(409, { detail: { error: "untransferred", message: "1 of 2 items have no one to transfer them to: Lead of the team Intel" } });
      return null;
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Disable ana" }));
    const panel = await screen.findByRole("group", { name: "Disable ana" });
    expect(within(panel).getByText("Not listed here yet: boards, proposed types.")).toBeTruthy();
    fireEvent.change(within(panel).getByRole("combobox", { name: "Transfer to, for Only Author of the case Kestrel" }), {
      target: { value: "u2" },
    });
    fireEvent.click(within(panel).getByRole("button", { name: "Transfer and disable ana" }));
    expect(await within(panel).findByRole("alert")).toBeTruthy();
    expect(within(panel).getByText(/Lead of the team Intel$/, { selector: "p" })).toBeTruthy();
    expect(sent.find((s) => s.path === "POST people/u1/disable")?.body).toEqual({
      transfers: [{ kind: "case_author", id: "c1", to: "u2" }],
    });
  });

  it("sends a transfer for every item once each has a recipient", async () => {
    const sent = serve((path) => {
      if (path === "people/u1/disable-plan") return json(200, PLAN);
      if (path === "people/u1/disable") return json(200, { ...ANA, enabled: false });
      return null;
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Disable ana" }));
    const panel = await screen.findByRole("group", { name: "Disable ana" });
    for (const item of PLAN.items)
      fireEvent.change(within(panel).getByRole("combobox", { name: `Transfer to, for ${item.label}` }), { target: { value: "u2" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Transfer and disable ana" }));
    expect(await screen.findByText("Disabled")).toBeTruthy();
    expect((sent.find((s) => s.path === "POST people/u1/disable")?.body as { transfers: unknown[] }).transfers).toHaveLength(2);
  });
});

describe("Admin › People's Disable… with L3.8's items (L2.5b, ADR-145 Amendment 8)", () => {
  const PLAN = { person: "u1", not_yet_listed: ["promotions waiting for review", "reviews waiting on them"],
                 items: [{ kind: "view", id: "v1", investigation_id: "c1", label: "A private view of the case Kestrel" },
                         { kind: "drawn_watch", id: "w1", investigation_id: "c1",
                           label: "A watch on an item they drew in the case Kestrel" }] };  // prettier-ignore
  const OWNED = (withheld: boolean) => ({ person: "u1", items: [], counts: {}, withheld, not_yet_listed: [] });
  const WORDS = "2 transferred, and those stand; not disabled yet: they still own items you may not see: an administrator who may see them, or an Author of their case, transfers them, and then you can disable them";

  it("offers a transfer for each of L3.8's items (a view and a watch here), and sends each by its kind", async () => {
    const sent = serve((path) => {
      if (path === "people/u1/disable-plan") return json(200, PLAN);
      if (path === "people/u1/ownership") return json(200, OWNED(false));
      if (path === "people/u1/disable") return json(200, { ...ANA, enabled: false });
      return null;
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Disable ana" }));
    const panel = await screen.findByRole("group", { name: "Disable ana" });
    for (const item of PLAN.items)
      fireEvent.change(await within(panel).findByRole("combobox", { name: `Transfer to, for ${item.label}` }), { target: { value: "u2" } });
    expect(within(panel).queryByRole("note", { name: "Items of ana you may not see" })).toBeNull();
    fireEvent.click(within(panel).getByRole("button", { name: "Transfer and disable ana" }));
    expect(await screen.findByText("Disabled")).toBeTruthy();
    expect(sent.some((s) => s.path === "GET people/u1/ownership")).toBe(true);
    expect(sent.find((s) => s.path === "POST people/u1/disable")?.body).toEqual({
      transfers: [{ kind: "view", id: "v1", to: "u2" }, { kind: "drawn_watch", id: "w1", to: "u2" }],
    });
  });

  it("says, naming nothing, that items are withheld, and shows the Conduit's refusal after the transfers", async () => {
    let posted = false;
    serve((path) => {
      if (path === "people/u1/disable-plan") return json(200, posted ? { ...PLAN, items: [] } : PLAN);
      if (path === "people/u1/ownership") return json(200, OWNED(true));
      if (path === "people/u1/disable") {
        posted = true;
        return json(409, { detail: { error: "withheld_items", message: WORDS } });
      }
      return null;
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Disable ana" }));
    const panel = await screen.findByRole("group", { name: "Disable ana" });
    const note = await within(panel).findByRole("note", { name: "Items of ana you may not see" });
    expect(note.textContent).toContain("ana stays enabled until an administrator who may see those items");
    for (const item of PLAN.items)
      fireEvent.change(within(panel).getByRole("combobox", { name: `Transfer to, for ${item.label}` }), { target: { value: "u2" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Transfer and disable ana" }));
    expect((await within(panel).findByRole("alert")).textContent).toContain("2 transferred, and those stand");
    // The plan is read again (review finding 5): the transferred items are no longer offered.
    await waitFor(() => expect(within(panel).queryByRole("combobox", { name: `Transfer to, for ${PLAN.items[0]?.label}` })).toBeNull());
  });

  it("says it could not check when the ownership read fails, never that nothing blocks", async () => {
    serve((path) => {
      if (path === "people/u1/disable-plan") return json(200, PLAN);
      if (path === "people/u1/ownership") return json(500, {});
      return null;
    });
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Disable ana" }));
    const panel = await screen.findByRole("group", { name: "Disable ana" });
    const note = await within(panel).findByRole("note", { name: "Items of ana you may not see" });
    expect(note.textContent).toContain("Could not check whether ana owns items you may not see.");
  });
});

describe("Admin › Roles (R2)", () => {
  it("offers every right, grouped by place, an ungrouped one under Other", () => {
    const groups = groupsFor(["investigate", "a_right_from_tomorrow"]);
    expect(groups.map((g) => g.label)).toEqual(["Investigation (the Glass)", "Other"]);
    const named = RIGHT_GROUPS.flatMap((g) => g.rights);
    expect(new Set(named).size).toBe(named.length);
  });

  it("copies a built-in role into a new one and shows the Conduit's refusal in its words", async () => {
    const sent = serve((path, init) =>
      path === "roles" && init?.method === "POST"
        ? json(409, { detail: { error: "forbidden_pair", message: "a role cannot hold both promote_to_dataset and review_promotions" } })
        : null,
    );
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Roles" }));
    fireEvent.click(await screen.findByRole("button", { name: "Copy Data Engineer into a new role" }));
    const form = screen.getByRole("form", { name: "New role" });
    expect((within(form).getByRole("checkbox", { name: "Review promotions" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(within(form).getByRole("button", { name: "Save new role" }));
    expect(await within(form).findByRole("alert")).toBeTruthy();
    expect(within(form).getByText(/cannot hold both promote_to_dataset and review_promotions/)).toBeTruthy();
    expect(sent.find((s) => s.path === "POST roles")?.body).toEqual({
      name: "Data Engineer (copy)",
      rights: ["edit_pipelines", "review_promotions"],
    });
  });

  it("names a team's lead from its members", async () => {
    const sent = serve((path) => (path === "teams/r1/lead" ? json(200, CATALOGUE.custom[0]?.team) : null));
    place(["manage_people"]);
    fireEvent.click(await screen.findByRole("button", { name: "Roles" }));
    fireEvent.click(await screen.findByRole("button", { name: "Team for Intel desk" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Lead of Intel" }), { target: { value: "u1" } });
    fireEvent.click(screen.getByRole("button", { name: "Hand over the lead of Intel" }));
    await waitFor(() => expect(sent.find((s) => s.path === "PUT teams/r1/lead")?.body).toEqual({ lead: "u1" }));
  });
});
