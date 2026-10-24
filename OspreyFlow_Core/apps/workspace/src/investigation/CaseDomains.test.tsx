// @vitest-environment jsdom
// ADR-126 decision 1: a case's domain models are shown to every reader of the case, and changed
// only by its Author, through `PATCH /v1/investigations/{id}`. The Conduit enforces who may (403 for
// anyone else); these prove the Glass offers the change to the Author alone and sends what was
// ticked.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaseDomains } from "./CaseDomains";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve(routes: Record<string, (init?: RequestInit) => Response>) {
  const calls: { key: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
      calls.push({ key, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const handler = routes[key];
      if (!handler) throw new Error(`unexpected ${key}`);
      return handler(init);
    }),
  );
  return calls;
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const listing = (level: string, domains: string[]) => () =>
  json(200, [{ id: "c1", name: "C", level, created_at: "", created_by: "", domains }]);

describe("CaseDomains", () => {
  it("shows the packs by label to a reader who is not the Author, and offers no change", async () => {
    serve({ "GET /v1/investigations": listing("editor", ["fibo", "niem"]) });
    render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    const section = await screen.findByRole("region", { name: "Domain models" });
    expect(await within(section).findByText("Financial fraud and AML (FIBO), Crime case analysis (NIEM)")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Change domain models" })).toBeNull());
  });

  it("offers no change to a Viewer either, and says POLE for a case with none", async () => {
    serve({ "GET /v1/investigations": listing("viewer", []) });
    render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    expect(await screen.findByText("Bespoke POLE (the core model)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Change domain models" })).toBeNull();
  });

  it("lets the Author change them, sending only the domains, and shows the packs afterwards", async () => {
    const calls = serve({
      "GET /v1/investigations": listing("author", []),
      "PATCH /v1/investigations/c1": () => json(200, { id: "c1", name: "C", domains: ["niem"] }),
    });
    const onChanged = vi.fn();
    render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Change domain models" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Crime case analysis (NIEM)" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls.find((c) => c.key === "PATCH /v1/investigations/c1")!.body).toEqual({ domains: ["niem"] });
    expect(await screen.findByText("Crime case analysis (NIEM)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("starts the Author's choice from the packs the case holds, and can choose none", async () => {
    const calls = serve({
      "GET /v1/investigations": listing("author", ["fibo"]),
      "PATCH /v1/investigations/c1": () => json(200, { id: "c1", name: "C", domains: [] }),
    });
    render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Change domain models" }));
    const fibo = screen.getByRole("checkbox", { name: "Financial fraud and AML (FIBO)" }) as HTMLInputElement;
    expect(fibo.checked).toBe(true);
    fireEvent.click(fibo);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.key === "PATCH /v1/investigations/c1")).toBe(true));
    expect(calls.find((c) => c.key === "PATCH /v1/investigations/c1")!.body).toEqual({ domains: [] });
  });

  it("says in words when the Conduit refuses, and keeps the packs it showed", async () => {
    serve({
      "GET /v1/investigations": listing("author", ["fibo"]),
      "PATCH /v1/investigations/c1": () => json(403, {}),
    });
    render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Change domain models" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Only the case's Author");
  });

  it("offers no change to an Author who does not hold share_case, and shows the packs read-only", async () => {
    serve({ "GET /v1/investigations": listing("author", ["niem"]) });
    render(
      <CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" rights={new Set(["investigate"])} />,
    );
    expect(await screen.findByText("Crime case analysis (NIEM)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Change domain models" })).toBeNull();
  });

  it("offers the change to an Author who holds share_case", async () => {
    serve({ "GET /v1/investigations": listing("author", []) });
    render(
      <CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" rights={new Set(["share_case"])} />,
    );
    expect(await screen.findByRole("button", { name: "Change domain models" })).toBeTruthy();
  });

  it("reads no listing of its own when it is given its entry, and shows what that says", async () => {
    const calls = serve({});
    const entry = { id: "c1", name: "C", level: "author" as const, created_at: "", created_by: "", domains: ["stix" as const] };
    render(<CaseDomains apiBaseUrl="http://api" bearerToken="t" investigationId="c1" entry={entry} />);
    expect(await screen.findByText("Cyber threat analytics (STIX 2.1)")).toBeTruthy();
    expect(calls).toHaveLength(0);
  });
});
