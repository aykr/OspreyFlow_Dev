// @vitest-environment jsdom
// ADR-145 Amendment 4 decision 12, as the owner ruled (c) on 9 November 2026 (L2.7): a tip or a refusal
// in Admin names the roles that hold a right, never people; and nothing Admin draws shows a role's or a
// right's id (`data_engineer`, `right:read_export_ledger`) where its name belongs. Every section that
// draws a tip or a grant is rendered here with synthetic people, and every tip (each element a control
// is described by), every refusal (`role="alert"`) and the whole of the text are read. Red with a
// preset's roles said by id, a grant said as its id, or a person's name put in a tip.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RIGHT_WORDS } from "../help/roles";
import { AdminPlace } from "./AdminPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const ANA = { id: "u1", username: "ana", name: "Ana Analyst", enabled: true, roles: ["analyst", "role:r1", "right:read_export_ledger"],
              clearance: "OFFICIAL", org_unit: "verify" };  // prettier-ignore
const BEA = { ...ANA, id: "u2", username: "bea", name: "Bea Engineer", roles: ["data_engineer"] };
const PEOPLE = [ANA, BEA];
const CATALOGUE = {
  built_in: [
    { id: "analyst", label: "Analyst", rights: ["investigate", "triage_alerts"], gives: [] },
    { id: "data_engineer", label: "Data Engineer", rights: ["edit_pipelines", "review_promotions"], gives: [] },
    { id: "osprey-admin", label: "Administrator", rights: ["administer_system"], gives: [] },
    { id: "super_user", label: "Super user", rights: ["investigate"], gives: ["analyst", "data_engineer", "rule_author"] },
  ],
  custom: [{ id: "r1", name: "Intel desk", version: 2, rights: ["investigate"], changed_by: "a", changed_at: "", holders: 1,
             team: { role_id: "r1", display_name: "Intel", mailbox: "intel@example.org", lead: "u1", cover: null,
                     cover_until: null, acting_lead: "u1", members: [{ id: "u1", name: "Ana Analyst" }] } }],
};  // prettier-ignore
const ROWS = { rows: [{ id: "u1", levels: [{ investigation_id: "c1", name: "Kestrel", level: "author", through: null }] }], without_author: [] };
const DATASET = { id: "ds-a", name: "Prison records", owning_unit: "verify", egress: "none", kind: "source",
                  promotion_policy: "second_person_reviews", highest_marking: null };  // prettier-ignore
const AUTHORS = { dataset_id: "ds-a", has_home_case: true, team: null,
                  people: [{ id: "u2", name: "Bea Engineer", approves: true }] };  // prettier-ignore

/** Every role id and every right id that no prose would hold: none is shown where its name belongs.
 * A one-word id (`analyst`, `export`, `investigate`) is left out as an English word, said in prose; a
 * grant is never shown as its id (`grantWords`), which `right:` and `role:` catch. */
const IDS = [
  "data_engineer", "osprey-admin", "reports_viewer", "rule_author", "super_user", "right:", "role:",
  ...Object.keys(RIGHT_WORDS).filter((r) => r.includes("_")),
]; // prettier-ignore
const PERSON_WORDS = PEOPLE.flatMap((p) => [p.id, p.username, p.name]);

function serve() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      if (path === "people") return json(200, PEOPLE);
      if (path === "people/rows") return json(200, ROWS);
      if (path === "roles") return json(200, CATALOGUE);
      if (path === "organisation-arrivals") return json(200, []);
      if (path === "datasets") return json(200, [DATASET]);
      if (path === "datasets/ds-a/authors") return json(200, AUTHORS);
      if (path === "datasets/ds-a/cases") return json(200, { dataset_id: "ds-a", cases: [] });
      if (path === "connections") return json(200, []);
      return json(200, []);
    }),
  );
}

const word = (w: string) => new RegExp(`(^|[^A-Za-z0-9_:-])${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "");

function tips(): { of: string; text: string }[] {
  return [...document.querySelectorAll("[aria-describedby]")].flatMap((el) =>
    (el.getAttribute("aria-describedby") ?? "")
      .split(/\s+/)
      .filter(Boolean)
      .map((id) => ({ of: el.getAttribute("aria-label") ?? el.textContent ?? "", text: document.getElementById(id)?.textContent ?? "" })),
  );
}

function check(where: string) {
  const all = document.body.textContent ?? "";
  for (const id of IDS) expect(all, `${where}: the id ${id} is shown`).not.toMatch(word(id));
  const said = [...tips(), ...screen.queryAllByRole("alert").map((a) => ({ of: "a refusal", text: a.textContent ?? "" }))];
  expect(said.length, `${where}: no tip was found, so nothing was checked`).toBeGreaterThan(0);
  for (const { of, text } of said) {
    expect(text.trim(), `${where}: ${of} is described by nothing`).not.toBe("");
    for (const person of PERSON_WORDS) expect(text, `${where}: ${of}'s tip names ${person}`).not.toMatch(word(person));
  }
}

const open = (rights: string[]) => render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);
const section = (name: string) =>
  fireEvent.click(within(screen.getByRole("navigation", { name: "Admin sections" })).getByRole("button", { name }));

describe("Admin's words: roles by name, never people or ids", () => {
  it("in People: each role's box, each person's levels and their grants", async () => {
    serve();
    open(["manage_people"]);
    await screen.findByText("Author of Kestrel");
    expect(screen.getByRole("checkbox", { name: "Data Engineer for bea" }).getAttribute("aria-describedby")).toBeTruthy();
    expect(screen.getByText(/Read export ledger \(a single right\)/)).toBeTruthy();
    check("People");
  });

  it("in Roles: the built-in and custom roles, a preset's roles and the team editor", async () => {
    serve();
    open(["manage_people"]);
    section("Roles");
    await screen.findByText("A preset: gives Analyst, Data Engineer, Rule author together");
    fireEvent.click(screen.getByRole("button", { name: "Team for Intel desk" }));
    await screen.findByRole("combobox", { name: "Lead of Intel" });
    expect(screen.getByRole("combobox", { name: "Lead of Intel" }).getAttribute("aria-describedby")).toBeTruthy();
    check("Roles");
  });

  it("in Datasets: a dataset's Authors and Change owner", async () => {
    serve();
    open(["administer_system"]);
    section("Datasets");
    fireEvent.click(await screen.findByRole("button", { name: "Details for Prison records" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Change owner of Prison records" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "Change owner of Prison records" }).getAttribute("aria-describedby")).toBeTruthy();
    check("Datasets");
  });
});
