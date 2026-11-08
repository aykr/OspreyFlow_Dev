// @vitest-environment jsdom
// ADR-126 Amendment 2: a case's domain models are shown to every reader of the case, read-only:
// they come from the dataset's domain model and change there, in the Ingest Studio. No one, the
// case's Author included, is offered a change here, and nothing is ever sent (the Conduit refuses a
// change of packs through the case, 409 `packs_from_the_model`).
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaseDomains, FROM_THE_DATASET } from "./CaseDomains";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve(routes: Record<string, () => Response>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
      calls.push(key);
      const handler = routes[key];
      if (!handler) throw new Error(`unexpected ${key}`);
      return handler();
    }),
  );
  return calls;
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const listing = (level: string, domains: string[]) => () =>
  json(200, [{ id: "c1", name: "C", level, created_at: "", created_by: "", domains }]);

describe("CaseDomains", () => {
  for (const level of ["author", "editor", "viewer"]) {
    it(`shows the packs read-only to an ${level}, saying they come from the dataset's domain model`, async () => {
      const calls = serve({ "GET /v1/investigations": listing(level, ["fibo", "niem"]) });
      render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
      const section = await screen.findByRole("region", { name: "Domain models" });
      expect(await within(section).findByText("Financial fraud and AML (FIBO), Crime case analysis (NIEM)")).toBeTruthy();
      expect(within(section).getByText(FROM_THE_DATASET)).toBeTruthy();
      expect(within(section).queryByRole("button")).toBeNull();
      expect(within(section).queryByRole("checkbox")).toBeNull();
      expect(calls.filter((c) => c.startsWith("PATCH"))).toEqual([]);
    });
  }

  it("says POLE for a case whose dataset's model carries no pack", async () => {
    serve({ "GET /v1/investigations": listing("author", []) });
    render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    expect(await screen.findByText("Bespoke POLE (the core model)")).toBeTruthy();
    expect(screen.getByText(FROM_THE_DATASET)).toBeTruthy();
  });

  it("uses the entry it is given, reading nothing itself", async () => {
    const calls = serve({});
    render(
      <CaseDomains
        apiBaseUrl="http://api"
        bearerToken="t"
        investigationId="c1"
        entry={{ id: "c1", name: "C", level: "author", created_at: "", created_by: "", domains: ["stix"] } as never}
      />,
    );
    expect(await screen.findByText(/STIX/)).toBeTruthy();
    expect(calls).toEqual([]);
  });

  it("says in words when the listing cannot be read", async () => {
    serve({ "GET /v1/investigations": () => json(500, {}) });
    render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    expect((await screen.findByRole("alert")).textContent).toBeTruthy();
  });
});
