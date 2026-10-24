// @vitest-environment jsdom
// The Cases drawer's two settings of the open case, "Data this case reads" and "Domain models", read
// the case's listing entry once between them (not once each), and read it again after either is
// changed, so what is shown afterwards is what the server now says.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaseSettings } from "./CaseSettings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function serve(level = "author") {
  const calls: string[] = [];
  let domains: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
      calls.push(key);
      if (key === "GET /v1/investigations")
        return json(200, [{ id: "c1", name: "C", level, created_at: "", created_by: "", domains }]);
      if (key === "GET /v1/investigations/c1/datasets") return json(200, [{ id: "enron", name: "Enron corpus", owning_unit: "u" }]);
      if (key === "PATCH /v1/investigations/c1") {
        domains = (JSON.parse(String(init?.body)) as { domains: string[] }).domains;
        return json(200, { id: "c1", name: "C", domains });
      }
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
    await screen.findByRole("button", { name: "Change domain models" });
    await screen.findByRole("button", { name: "Change what this case reads" });
    expect(listingReads(calls)).toBe(1);
  });

  it("offers neither change to an Author without share_case, and both packs and data are still shown", async () => {
    serve();
    render(<CaseSettings apiBaseUrl="http://api" bearerToken="t" investigationId="c1" rights={new Set(["investigate"])} />);
    expect(await screen.findByText("Enron corpus · enron")).toBeTruthy();
    expect(screen.getByText("Bespoke POLE (the core model)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Change domain models" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Change what this case reads" })).toBeNull();
  });

  it("reads the listing again after the packs are changed, and shows what that read says", async () => {
    const calls = serve();
    const onChanged = vi.fn();
    render(<CaseSettings apiBaseUrl="http://api" bearerToken="t" investigationId="c1" rights={null} onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Change domain models" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Crime case analysis (NIEM)" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(listingReads(calls)).toBe(2);
    expect(calls.lastIndexOf("GET /v1/investigations")).toBeGreaterThan(calls.indexOf("PATCH /v1/investigations/c1"));
    const section = screen.getByRole("region", { name: "Domain models" });
    expect(within(section).getByText("Crime case analysis (NIEM)")).toBeTruthy();
  });
});
