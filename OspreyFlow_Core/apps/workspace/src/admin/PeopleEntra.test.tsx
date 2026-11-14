// @vitest-environment jsdom
// ADR-148 Amendment 8: Admin › People on Entra ID sign-in. Entra holds the accounts, so People says so,
// adds a person by object id instead of inviting, and offers no access, sign-in reset or removal; the
// Conduit refuses those anyway (test_entra_people.py). Keycloak's People is unchanged (the control).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "./AdminPlace";
import { ENTRA_PEOPLE_WORDS, GUEST_WORDS } from "./sections/People";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const OID = "50000000-0000-4000-8000-000000000001";
const NEW = "50000000-0000-4000-8000-000000000002";
const ANA = { id: OID, username: "ana@example.test", name: "Ana Analyst", enabled: true, roles: ["analyst"],
              clearance: "OFFICIAL", org_unit: "verify" };  // prettier-ignore

function serve(kind: "entra" | "keycloak", handler: (path: string, init?: RequestInit) => Response | null = () => null) {
  const sent: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname.replace("/v1/admin/", "");
      sent.push({ path: `${init?.method ?? "GET"} ${path}`, body: init?.body ? JSON.parse(String(init.body)) : null });
      const answered = handler(path, init);
      if (answered) return answered;
      if (path === "sign-in") return json(200, { kind });
      if (path === "people") return json(200, [ANA]);
      if (path === "people/rows") return json(200, { rows: [], without_author: [] });
      if (path === "roles") return json(200, { built_in: [], custom: [] });
      if (path === "organisation-arrivals") return json(200, []);
      return json(200, {});
    }),
  );
  return sent;
}

const place = () => render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["manage_people"])} />);

describe("Admin › People on Entra ID sign-in", () => {
  it("says Entra holds the accounts and offers add by object id, never invite, access, reset or remove", async () => {
    serve("entra");
    place();
    expect(await screen.findByText(ENTRA_PEOPLE_WORDS)).toBeTruthy();
    expect(screen.getByRole("form", { name: "Add a person by object id" })).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Invite a person" })).toBeNull();
    expect(screen.queryByLabelText(`Edit access for ${ANA.username}`)).toBeNull();
    expect(screen.queryByLabelText(`Reset sign-in for ${ANA.username}`)).toBeNull();
    expect(screen.queryByLabelText(`Remove ${ANA.username}`)).toBeNull();
    // Roles and Disable stay this deployment's.
    expect(screen.getByLabelText(`Save roles for ${ANA.username}`)).toBeTruthy();
    expect(screen.getByLabelText(`Disable ${ANA.username}`)).toBeTruthy();
  });

  it("adds a person by object id, who joins the list with no roles", async () => {
    const sent = serve("entra", (path, init) =>
      path === "people/by-object-id" && init?.method === "POST"
        ? json(201, { id: NEW, username: NEW, name: NEW, enabled: true, roles: [] })
        : null,
    );
    place();
    fireEvent.change(await screen.findByLabelText("Entra object id"), { target: { value: ` ${NEW} ` } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText(`${NEW} was added with no roles. Give them roles below; they hold them from their first sign-in.`)).toBeTruthy();
    expect(sent.find((s) => s.path === "POST people/by-object-id")?.body).toEqual({ object_id: NEW });
  });

  it("shows the Conduit's refusal in its words", async () => {
    serve("entra", (path) =>
      path === "people/by-object-id" ? json(409, { error: "person_exists", detail: "that person is already here" }) : null,
    );
    place();
    fireEvent.change(await screen.findByLabelText("Entra object id"), { target: { value: OID } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
  });
});

describe("Admin › People on Keycloak (the control)", () => {
  it("invites, and offers access, reset and remove, with no Entra words", async () => {
    serve("keycloak");
    place();
    expect(await screen.findByRole("form", { name: "Invite a person" })).toBeTruthy();
    expect(screen.queryByText(ENTRA_PEOPLE_WORDS)).toBeNull();
    expect(screen.queryByRole("form", { name: "Add a person by object id" })).toBeNull();
    expect(screen.getByLabelText(`Edit access for ${ANA.username}`)).toBeTruthy();
    expect(screen.getByLabelText(`Reset sign-in for ${ANA.username}`)).toBeTruthy();
  });

  it("keeps Keycloak's People when the sign-in kind cannot be read", async () => {
    serve("keycloak", (path) => (path === "sign-in" ? json(500, {}) : null));
    place();
    expect(await screen.findByRole("form", { name: "Invite a person" })).toBeTruthy();
  });
});

// ADR-148 Amendment 17: guest (B2B) accounts admitted behind a setting, switched here by an administrator of people.
describe("Admin › People's guests on Entra ID", () => {
  it("shows guests not admitted, and admits them when the box is ticked", async () => {
    const sent = serve("entra", (path, init) =>
      path === "sign-in/guests"
        ? json(200, { admitted: init?.method === "PUT" ? (JSON.parse(String(init.body)) as { admitted: boolean }).admitted : false })
        : null,
    );
    place();
    const box = (await screen.findByLabelText("Admit guest accounts")) as HTMLInputElement;
    await waitFor(() => expect(box.disabled).toBe(false));
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    await waitFor(() => expect(box.checked).toBe(true));
    expect(sent.filter((s) => s.path === "PUT sign-in/guests")).toEqual([{ path: "PUT sign-in/guests", body: { admitted: true } }]);
  });

  it("shows the Conduit's refusal of turning guests off in its words, the box left as it was", async () => {
    serve("entra", (path, init) => {
      if (path !== "sign-in/guests") return null;
      if (init?.method === "PUT") return json(409, { detail: { error: "locks_out_administrators", message: "this would leave nobody able to manage people" } });
      return json(200, { admitted: true });
    });
    place();
    const box = (await screen.findByLabelText("Admit guest accounts")) as HTMLInputElement;
    await waitFor(() => expect(box.checked).toBe(true));
    fireEvent.click(box);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("this would leave nobody able to manage people"));
    expect(box.checked).toBe(true);
  });

  it("marks a guest in the list", async () => {
    serve("entra", (path) => (path === "people" ? json(200, [{ ...ANA, guest: true }]) : null));
    place();
    expect(await screen.findByText(GUEST_WORDS)).toBeTruthy();
  });

  it("offers no guest setting on Keycloak", async () => {
    serve("keycloak");
    place();
    expect(await screen.findByRole("form", { name: "Invite a person" })).toBeTruthy();
    expect(screen.queryByLabelText("Admit guest accounts")).toBeNull();
  });
});
