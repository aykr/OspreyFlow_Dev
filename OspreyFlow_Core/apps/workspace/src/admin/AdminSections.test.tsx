// @vitest-environment jsdom
// ADR-145 decisions 5 and 13, ADR-110 Amendment 14: the Admin place as a side list of sections in
// their groups, each shown only to a holder of its right; a section not built yet is a "coming"
// placeholder that calls nothing. That each built section's routes refuse a principal without its
// right is the Conduit's, proved in `test_admin_sections.py` from the routes' own checks (rule 3:
// this hiding is never the control).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ADMIN_GROUPS, AdminPlace, SCREENS, sectionsFor } from "./AdminPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-brand");
});

/** Every call answered empty, and counted. */
function serve(): string[] {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      asked.push(new URL(url).pathname);
      return new Response(JSON.stringify(url.endsWith("/system") ? { components: [] } : []), { status: 200 });
    }),
  );
  return asked;
}

function place(rights: string[]) {
  render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(rights)} />);
  return within(screen.getByRole("navigation", { name: "Admin sections" }));
}

/** The side list as read: each group's heading, then its sections' names. */
function listed(): string[] {
  const nav = screen.getByRole("navigation", { name: "Admin sections" });
  return [...nav.querySelectorAll("h3, button")].map((el) => (el.tagName === "H3" ? `# ${el.textContent}` : el.textContent!));
}

const ALL = [...new Set(ADMIN_GROUPS.flatMap((g) => g.sections.map((s) => s.right)))];

describe("the Admin place's sections (ADR-145 decision 5)", () => {
  it("are decision 5's groups and sections, in its order", () => {
    serve();
    place(ALL);
    expect(listed()).toEqual([
      "# People", "People and roles", "Roles", "Dashboard identities",
      "# Data", "Datasets", "Connections", "Proposed types",
      "# Running", "Operations", "System", "Models", "Maps",
      "# Policies", "Grading scheme (coming)", "Approval rights (coming)", "Uploads (coming)",
      "Audit",
      "Demo packs",
    ]); // prettier-ignore
  });

  it.each(ALL)("shows a holder of %s only the sections of that right", (right) => {
    serve();
    place([right]);
    const expected = ADMIN_GROUPS.flatMap((g) => g.sections).filter((s) => s.right === right);
    const names = screen.getAllByRole("button").filter((b) => b.closest("nav")).map((b) => b.textContent);
    expect(names).toEqual(expected.map((s) => (s.coming ? `${s.label} (coming)` : s.label)));
  });

  it("shows nothing to a person holding no right of a section", () => {
    serve();
    render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["investigate", "edit_pipelines"])} />);
    expect(screen.queryByRole("navigation", { name: "Admin sections" })).toBeNull();
    expect(screen.getByText("Your account holds no administration right.")).toBeTruthy();
  });

  it("draws each built section from its screen, and a placeholder from none", () => {
    const sections = ADMIN_GROUPS.flatMap((g) => g.sections);
    expect(Object.keys(SCREENS).sort()).toEqual(sections.filter((s) => s.screen).map((s) => s.id).sort());
    for (const s of sections) expect(Boolean(s.screen) !== Boolean(s.coming)).toBe(true);
  });

  it("opens the first built section the person holds", async () => {
    serve();
    place(["manage_people"]);
    expect(screen.getByRole("heading", { name: "People and roles" })).toBeTruthy();
  });

  it("opens a placeholder from the side list and asks the Conduit nothing for it", async () => {
    const asked = serve();
    const nav = place(["administer_system"]);
    await waitFor(() => expect(asked).toContain("/v1/admin/datasets"));
    const before = asked.length;
    fireEvent.click(nav.getByRole("button", { name: "Uploads (coming)" }));
    expect(screen.getByRole("heading", { name: "Uploads" })).toBeTruthy();
    expect(screen.getByText(/^Coming: The largest picture/)).toBeTruthy();
    expect(asked.length).toBe(before);
  });

  // ADR-145 Amendment 3 decision 3: once Audit is built, `read_audit` alone opens it, and it reads.
  it("opens Audit for a holder of read_audit alone, which reads the audit", async () => {
    const asked = serve();
    const nav = place(["read_audit"]);
    expect(screen.getByRole("heading", { name: "Audit" })).toBeTruthy();
    // Audit alone: no other section is offered for read_audit.
    expect(nav.getAllByRole("button").map((b) => b.textContent)).toEqual(["Audit"]);
    await waitFor(() => expect(asked).toContain("/v1/admin/audit"));
  });

  it("opens a section from the side list, marks it current, and moves focus to its heading", async () => {
    const asked = serve();
    const nav = place(["manage_people", "manage_dashboards"]);
    const roles = nav.getByRole("button", { name: "Roles" });
    expect(nav.getByRole("button", { name: "People and roles" }).getAttribute("aria-current")).toBe("page");
    fireEvent.click(roles);
    expect(roles.getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("button", { name: "People and roles" }).getAttribute("aria-current")).toBeNull();
    const heading = screen.getByRole("heading", { name: "Roles" });
    expect(document.activeElement).toBe(heading);
    // L2.5: Roles is built, and reads the roles when it opens.
    await waitFor(() => expect(asked.some((a) => a.endsWith("/v1/admin/roles"))).toBe(true));
    fireEvent.click(nav.getByRole("button", { name: "Dashboard identities" }));
    expect(await screen.findByRole("table", { name: "Dashboard identities" })).toBeTruthy();
  });

  it("lists the sections a person's rights show, by sectionsFor", () => {
    expect(sectionsFor(new Set(["operate_schedules"])).map((g) => [g.label, g.sections.map((s) => s.id)])).toEqual([
      ["Running", ["operations"]],
    ]);
    expect(sectionsFor(new Set())).toEqual([]);
  });
});

describe("under the GOV.UK brand (ADR-145 decision 13)", () => {
  it("is a GOV.UK side navigation: GOV.UK headings and links, the open one current", () => {
    document.documentElement.setAttribute("data-brand", "govuk");
    serve();
    place(["administer_system"]);
    const nav = screen.getByRole("navigation", { name: "Admin sections" });
    expect(nav.classList.contains("admin-nav--govuk")).toBe(true);
    expect([...nav.querySelectorAll("h3")].every((h) => h.classList.contains("govuk-heading-s"))).toBe(true);
    const links = within(nav).getAllByRole("button");
    expect(links.every((b) => b.classList.contains("govuk-link"))).toBe(true);
    expect(links.filter((b) => b.getAttribute("aria-current") === "page").map((b) => b.textContent)).toEqual(["Datasets"]);
  });
});
