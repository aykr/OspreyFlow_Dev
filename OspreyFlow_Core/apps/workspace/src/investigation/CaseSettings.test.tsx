// @vitest-environment jsdom
// The Cases drawer's two settings of the open case, "Data this case reads" and "Domain models", read
// the case's listing entry once between them (not once each). The domain models are read-only
// (ADR-126 Amendment 2): no change of them is offered, and nothing is sent.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FROM_THE_DATASET } from "./CaseDomains";
import { CaseSettings } from "./CaseSettings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function serve(level = "author") {
  const calls: string[] = [];
  const domains: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
      calls.push(key);
      if (key === "GET /v1/investigations")
        return json(200, [{ id: "c1", name: "C", level, created_at: "", created_by: "", domains }]);
      if (key === "GET /v1/investigations/c1/datasets") return json(200, [{ id: "enron", name: "Enron corpus", owning_unit: "u" }]);
      throw new Error(`unexpected ${key}`);
    }),
  );
  return calls;
}

const listingReads = (calls: string[]) => calls.filter((c) => c === "GET /v1/investigations").length;

describe("CaseSettings", () => {
  it("reads the case's listing once for both settings", async () => {
    const calls = serve();
    render(<CaseSettings apiBaseUrl="http://api" bearerToken="t" investigationId="c1" rights={new Set(["share_case"])} />);
    await screen.findByText(FROM_THE_DATASET);
    await screen.findByRole("button", { name: "Change what this case reads" });
    expect(listingReads(calls)).toBe(1);
  });

  it("offers neither change to an Author without share_case, and both packs and data are still shown", async () => {
    serve();
    render(<CaseSettings apiBaseUrl="http://api" bearerToken="t" investigationId="c1" rights={new Set(["investigate"])} />);
    expect(await screen.findByText("Enron corpus · enron")).toBeTruthy();
    expect(screen.getByText("Bespoke POLE (the core model)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Change what this case reads" })).toBeNull();
  });

  it("offers no change of the domain models, even to an Author with share_case", async () => {
    const calls = serve();
    render(<CaseSettings apiBaseUrl="http://api" bearerToken="t" investigationId="c1" rights={null} />);
    const section = await screen.findByRole("region", { name: "Domain models" });
    expect(await within(section).findByText(FROM_THE_DATASET)).toBeTruthy();
    expect(within(section).queryByRole("button")).toBeNull();
    expect(calls.some((c) => c.startsWith("PATCH"))).toBe(false);
  });
});
