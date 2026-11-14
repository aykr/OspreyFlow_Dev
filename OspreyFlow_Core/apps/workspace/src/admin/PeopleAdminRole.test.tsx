// @vitest-environment jsdom
// Route A2 (v0.5.2; studio's demo research, 14 November 2026): People and roles offers only the changes the giver
// may make. The Conduit refuses a change that newly gives an administration right its giver does not hold
// (`_may_give`: the rights of the roles as they would stand, less those the person's roles give now; ADR-145
// Amendment 5). The Glass decides each box, the Super user preset and the invitation the same way, so it neither
// offers what the Conduit refuses nor withholds what it allows. A box not offered stays in the Tab order
// (`aria-disabled`), refuses the change, and says its own why.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "./AdminPlace";
import { WITHHELD_RULE } from "./sections/People";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const person = (id: string, username: string, roles: string[]) =>
  ({ id, username, name: username, enabled: true, roles, clearance: "OFFICIAL", org_unit: "unit-1" });
const BEA = person("u2", "bea", ["data_engineer"]);
const ADA = person("u3", "ada", ["osprey-admin"]);
const CY = person("u4", "cy", ["right:read_audit"]);
const CATALOGUE = {
  built_in: [
    { id: "analyst", label: "Analyst", rights: ["investigate"], gives: [] },
    // As the real catalogue: Data Engineer carries Operate schedules, an administration right.
    { id: "data_engineer", label: "Data Engineer", rights: ["edit_pipelines", "operate_schedules"], gives: [] },
    { id: "osprey-admin", label: "Admin", rights: ["administer_system", "manage_people", "operate_schedules", "read_audit"], gives: [] },
    { id: "rule_author", label: "Rule author", rights: ["author_rules"], gives: [] },
  ],
  custom: [
    { id: "r9", name: "Admin desk", version: 1, rights: ["administer_system"], changed_by: "a", changed_at: "", holders: 0, team: null },
    { id: "r7", name: "Audit desk", version: 1, rights: ["read_audit", "investigate"], changed_by: "a", changed_at: "", holders: 0, team: null },
    { id: "r1", name: "Intel desk", version: 1, rights: ["investigate"], changed_by: "a", changed_at: "", holders: 0, team: null },
  ],
};  // prettier-ignore

function serve() {
  const sent: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      if (init?.method === "PUT") sent.push(`${path} ${String(init.body)}`);
      if (path === "people") return json(200, [BEA, ADA, CY]);
      if (path === "people/rows") return json(200, { rows: [], without_author: [] });
      if (path === "roles") return json(200, CATALOGUE);
      if (path === "organisation-arrivals") return json(200, []);
      return json(200, {});
    }),
  );
  return sent;
}

const place = (rights: string[]) =>
  render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);
const box = (name: string) => screen.findByRole("checkbox", { name }) as Promise<HTMLInputElement>;
const why = (el: HTMLElement) =>
  (el.getAttribute("aria-describedby") ?? "").split(" ").map((id) => document.getElementById(id)?.textContent ?? "").join(" ");
const notOffered = (el: HTMLElement) => el.getAttribute("aria-disabled") === "true";

describe("People and roles offers only what the giver may give (route A2)", () => {
  it("a people manager alone is not offered Admin, and each box says why, by the screens' names for rights", async () => {
    serve();
    place(["manage_people"]);
    const admin = await box("Admin for cy");
    expect(notOffered(admin)).toBe(true);
    expect(admin.disabled).toBe(false); // still reached by Tab
    expect(why(admin)).toContain(
      "You cannot give Admin here: it would give Administer system and Operate schedules, which you do not hold.");
    fireEvent.click(admin);
    expect(admin.checked).toBe(false); // the change is refused
    expect(screen.getByText(WITHHELD_RULE)).toBeTruthy();
    expect(notOffered(await box("Admin desk for cy"))).toBe(true);
    expect(notOffered(await box("Data Engineer for cy"))).toBe(true);
    expect(why(await box("Invite as Admin"))).toContain(
      "You cannot give Admin here: it would give Administer system, Operate schedules and Read audit, which you do not hold.");
    // What they may give stays offered.
    expect(notOffered(await box("Analyst for cy"))).toBe(false);
    expect(notOffered(await box("Intel desk for cy"))).toBe(false);
    expect(notOffered(await box("Invite as Analyst"))).toBe(false);
  });

  it("a right the person holds already, by any role or grant, is not newly given, so the role is offered", async () => {
    serve();
    place(["manage_people"]);
    // ada's Admin gives Operate schedules: Data Engineer gives her nothing new.
    expect(notOffered(await box("Data Engineer for ada"))).toBe(false);
    // cy's single grant gives Read audit: the Audit desk gives her nothing new; bea has no such grant.
    expect(notOffered(await box("Audit desk for cy"))).toBe(false);
    expect(notOffered(await box("Audit desk for bea"))).toBe(true);
    // A box already ticked can be unticked: that gives nothing.
    const held = await box("Admin for ada");
    expect(held.checked && !notOffered(held)).toBe(true);
    fireEvent.click(held);
    expect(held.checked).toBe(false);
    // ...and ticked again, since she held it when the row was read.
    fireEvent.click(held);
    expect(held.checked).toBe(true);
  });

  it("the Super user preset is decided whole: it gives Data Engineer's Operate schedules, so it is not offered", async () => {
    const sent = serve();
    place(["manage_people"]);
    const preset = (await screen.findByRole("button", { name: "Super user preset for cy" })) as HTMLButtonElement;
    expect(preset.getAttribute("aria-disabled")).toBe("true");
    expect(why(preset)).toContain("You cannot give the Super user preset here: it would give Operate schedules");
    fireEvent.click(preset);
    expect((await box("Data Engineer for cy")).checked).toBe(false);
    // bea holds Data Engineer already: the preset gives her nothing she lacks.
    const theirs = screen.getByRole("button", { name: "Super user preset for bea" });
    expect(theirs.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(theirs);
    expect((await box("Rule author for bea")).checked).toBe(true);
    expect(sent).toEqual([]);
  });

  it("an administrator is offered every role, and nothing is said", async () => {
    serve();
    place(["manage_people", "administer_system", "read_audit", "operate_schedules"]);
    expect(notOffered(await box("Admin for cy"))).toBe(false);
    expect(notOffered(await box("Admin desk for bea"))).toBe(false);
    expect(notOffered(await box("Invite as Admin"))).toBe(false);
    expect(screen.queryByText(WITHHELD_RULE)).toBeNull();
    expect(document.querySelector("[aria-disabled]")).toBeNull();
  });

  it("the offer follows the giver's rights when they are read again", async () => {
    serve();
    const view = place(["manage_people"]);
    expect(notOffered(await box("Admin for cy"))).toBe(true);
    view.rerender(<AdminPlace apiBaseUrl="http://x" bearerToken="t"
                              rights={new Set(["manage_people", "administer_system", "read_audit", "operate_schedules"])} />);  // prettier-ignore
    expect(notOffered(await box("Admin for cy"))).toBe(false);
  });
});
