// @vitest-environment jsdom
// ADR-148 Amendment 15: Admin › People on Entra ID with the proof of concept's administrator fallback. Where the
// Conduit says the deployment sets values itself (`GET /v1/admin/sign-in`'s `administrator_sets`), People says so in
// words and offers Access for those values alone; the values Entra sends are shown and sent back unchanged. Without
// the fallback, Entra's People is as before (no Access; PeopleEntra.test.tsx). The Conduit and the people store hold
// the limits (test_entra_people_administrator_access.py); here, what the screen offers and sends.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "./AdminPlace";
import { entraPeopleWords, ENTRA_PEOPLE_WORDS } from "./sections/People";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const OID = "50000000-0000-4000-8000-000000000002";
const ANA = { id: OID, username: "ana@example.test", name: "Ana Analyst", enabled: true, roles: ["analyst"],
              clearance: "OFFICIAL", org_unit: "unit-1", receivable_handling_codes: ["P"] };  // prettier-ignore

function serve(administratorSets: string[], handler: (path: string, init?: RequestInit) => Response | null = () => null) {
  const sent: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const full = new URL(url).pathname;
      if (full === "/v1/handling-scheme")
        return json(200, { classification: ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE"], handling_codes: { P: {}, R: {} } });
      const path = full.replace("/v1/admin/", "");
      sent.push({ path: `${init?.method ?? "GET"} ${path}`, body: init?.body ? JSON.parse(String(init.body)) : null });
      const answered = handler(path, init);
      if (answered) return answered;
      if (path === "sign-in") return json(200, { kind: "entra", administrator_sets: administratorSets });
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

describe("Admin › People on Entra ID with the administrator fallback", () => {
  it("says which values are set here, and Access offers those alone, sending Entra's back unchanged", async () => {
    const sent = serve(["clearance", "org_unit"], (path, init) =>
      path === `people/${OID}/access` && init?.method === "PUT"
        ? json(200, { ...ANA, ...JSON.parse(String(init.body)) })
        : null,
    );
    place();
    expect(await screen.findByText(entraPeopleWords(["clearance", "org_unit"]))).toBeTruthy();
    fireEvent.click(await screen.findByLabelText(`Edit access for ${ANA.username}`));
    await waitFor(() => expect(screen.getByRole("option", { name: "OFFICIAL-SENSITIVE" })).toBeTruthy());
    fireEvent.change(screen.getByLabelText(`Clearance for ${ANA.username}`), { target: { value: "OFFICIAL-SENSITIVE" } });
    fireEvent.change(screen.getByLabelText(`Unit for ${ANA.username}`), { target: { value: "unit-2" } });
    expect(screen.queryByLabelText(`Handling code R for ${ANA.username}`)).toBeNull();
    expect(screen.getByText("Handling codes P, from Entra ID")).toBeTruthy();
    fireEvent.click(screen.getByLabelText(`Save access for ${ANA.username}`));
    await screen.findByText("Saved.");
    // Entra's codes are not given, so never changed or checked by the Conduit.
    expect(sent.find((s) => s.path === `PUT people/${OID}/access`)?.body).toEqual({
      clearance: "OFFICIAL-SENSITIVE",
      org_unit: "unit-2",
    });
  });

  it("shows the Conduit's refusal, a clearance above the setter's own, in its words", async () => {
    serve(["clearance", "org_unit", "handling_codes"], (path, init) =>
      path === `people/${OID}/access` && init?.method === "PUT"
        ? json(403, { detail: { error: "above_your_clearance", clearance: "OFFICIAL-SENSITIVE" } })
        : null,
    );
    place();
    fireEvent.click(await screen.findByLabelText(`Edit access for ${ANA.username}`));
    await waitFor(() => expect(screen.getByRole("option", { name: "OFFICIAL-SENSITIVE" })).toBeTruthy());
    fireEvent.click(screen.getByLabelText(`Save access for ${ANA.username}`));
    expect(await screen.findByText("You cannot give a clearance above your own (OFFICIAL-SENSITIVE asked).")).toBeTruthy();
    expect(screen.queryByText("Saved.")).toBeNull();
  });

  it("without the fallback, Entra's People offers no Access (the control)", async () => {
    serve([]);
    place();
    expect(await screen.findByText(ENTRA_PEOPLE_WORDS)).toBeTruthy();
    expect(screen.queryByLabelText(`Edit access for ${ANA.username}`)).toBeNull();
  });

  it("says one value in the singular, every value in a list", () => {
    expect(entraPeopleWords(["clearance"])).toContain("Their clearance is set here");
    expect(entraPeopleWords(["clearance", "org_unit", "handling_codes"])).toContain(
      "Their clearance, unit and handling codes are set here",
    );
  });
});
