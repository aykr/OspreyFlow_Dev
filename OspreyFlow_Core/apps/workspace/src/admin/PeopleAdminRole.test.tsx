// @vitest-environment jsdom
// Route A2 (v0.5.2; studio's demo research, 14 November 2026): the Glass offers only the roles the giver may give.
// The Conduit refuses an administration right newly given by someone who does not hold it (`_may_give`,
// `custom_roles.giver_may_give`, ADR-145 Amendment 5); People and roles draws such a role not offered, and says
// who can give it, rather than offering it and showing the refusal on Save. A role the person already holds stays
// offered, since taking it away gives nothing.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "./AdminPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const person = (id: string, username: string, roles: string[]) =>
  ({ id, username, name: username, enabled: true, roles, clearance: "OFFICIAL", org_unit: "unit-1" });
const BEA = person("u2", "bea", ["data_engineer"]);
const ADA = person("u3", "ada", ["osprey-admin"]);
const ADMIN_RIGHTS = ["administer_system", "manage_people", "read_audit"];
const CATALOGUE = {
  built_in: [
    { id: "analyst", label: "Analyst", rights: ["investigate"], gives: [] },
    { id: "data_engineer", label: "Data Engineer", rights: ["edit_pipelines", "operate_schedules"], gives: [] },
    { id: "osprey-admin", label: "Admin", rights: ADMIN_RIGHTS, gives: [] },
  ],
  custom: [{ id: "r9", name: "Admin desk", version: 1, rights: ["administer_system"], changed_by: "a", changed_at: "",
             holders: 0, team: null },
           { id: "r1", name: "Intel desk", version: 1, rights: ["investigate"], changed_by: "a", changed_at: "",
             holders: 0, team: null }],
};  // prettier-ignore

function serve() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      if (path === "people") return json(200, [BEA, ADA]);
      if (path === "people/rows") return json(200, { rows: [], without_author: [] });
      if (path === "roles") return json(200, CATALOGUE);
      if (path === "organisation-arrivals") return json(200, []);
      return json(200, {});
    }),
  );
}

const place = (rights: string[]) => render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);
const box = (name: string) => screen.findByRole("checkbox", { name }) as Promise<HTMLInputElement>;
const WORDS = "You cannot give Admin: it carries Administer system and Read audit, which you do not hold.";

describe("People and roles offers only what the giver may give (route A2)", () => {
  it("a people manager alone is not offered Admin, nor a custom role carrying Administer system, and is told who can", async () => {
    serve();
    place(["manage_people"]);
    const admin = await box("Admin for bea");
    expect(admin.disabled).toBe(true);
    expect((await box("Admin desk for bea")).disabled).toBe(true);
    expect((await box("Invite as Admin")).disabled).toBe(true);
    const note = screen.getByText(WORDS, { exact: false });
    expect(note.textContent).toContain("You cannot give Admin desk: it carries Administer system, which you do not hold.");
    expect(admin.getAttribute("aria-describedby")?.split(" ")).toContain(note.id);
    // Data Engineer carries Operate schedules, an administration right too: not offered to give, but bea, who
    // holds it already, keeps hers offered.
    expect((await box("Invite as Data Engineer")).disabled).toBe(true);
    expect(note.textContent).toContain("You cannot give Data Engineer: it carries Operate schedules, which you do not hold.");
    expect((await box("Data Engineer for bea")).disabled).toBe(false);
    // What they may give stays offered.
    expect((await box("Analyst for bea")).disabled).toBe(false);
    expect((await box("Intel desk for bea")).disabled).toBe(false);
    expect((await box("Invite as Analyst")).disabled).toBe(false);
  });

  it("a person who already holds Admin keeps the box offered: taking it away gives nothing", async () => {
    serve();
    place(["manage_people"]);
    const admin = await box("Admin for ada");
    expect(admin.checked).toBe(true);
    expect(admin.disabled).toBe(false);
  });

  it("an administrator is offered Admin, and nothing is said", async () => {
    serve();
    place(["manage_people", "administer_system", "read_audit", "operate_schedules"]);
    expect((await box("Admin for bea")).disabled).toBe(false);
    expect((await box("Admin desk for bea")).disabled).toBe(false);
    expect((await box("Invite as Admin")).disabled).toBe(false);
    expect(screen.queryByText(/You cannot give/)).toBeNull();
  });

  it("each administration right the giver lacks is named, as the screens name rights", async () => {
    serve();
    place(["manage_people", "administer_system", "operate_schedules"]); // not read_audit: Admin carries it
    await box("Admin for bea");
    expect(screen.getByText(/You cannot give Admin: it carries Read audit, which you do not hold\./)).toBeTruthy();
    expect((await box("Admin desk for bea")).disabled).toBe(false);
  });
});
