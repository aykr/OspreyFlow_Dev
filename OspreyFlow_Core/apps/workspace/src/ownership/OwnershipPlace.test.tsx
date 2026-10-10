// @vitest-environment jsdom
// ADR-109 phase C: the Ownership place. It names the beneficial owners, every party's cumulative
// share (a partly unknown share said as "at least"), each chain in words, a circle of
// cross-holdings, and refuses a structure too deep in the server's words.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OwnershipPlace } from "./OwnershipPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function node(id: string, type: string, props: Record<string, unknown>) {
  return {
    id, type, properties: props,
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  };  // prettier-ignore
}

function edge(id: string, type: string, source: string, target: string, percent?: number) {
  return { id, type, source, target, properties: percent === undefined ? {} : { percent } };
}

const VIEW = {
  trace: {
    target: "C", threshold: 25,
    owners: [
      { node_id: "T", node_type: "Organisation", cumulative_percent: 90, paths: [{ link_ids: ["e1"], kind: "ownership", share: 90 }] },
      { node_id: "P", node_type: "Person", cumulative_percent: 47.8, beneficial_owner: true,
        paths: [{ link_ids: ["e2"], kind: "ownership", share: 10 }, { link_ids: ["e3", "e4", "e1"], kind: "ownership", share: 37.8 }] },
      { node_id: "K", node_type: "Organisation", cumulative_percent: 0, share_unknown: true, paths: [{ link_ids: ["e5", "e1"], kind: "unknown" }] },
    ],
    cycles: [["A", "T"]],
  },
  nodes: [
    node("C", "Organisation", { name: "Crescent Imports Ltd" }),
    node("T", "Organisation", { name: "Tamarind Holdings Ltd" }),
    node("A", "Organisation", { name: "Aegean Fiduciary Trust" }),
    node("P", "Person", { family_name: "Petrov", given_names: "Elena" }),
    node("K", "Organisation", { name: "Kestrel Nominees Ltd" }),
  ],
  edges: [
    edge("e1", "BENEFICIAL_OWNER_OF", "T", "C", 90),
    edge("e2", "BENEFICIAL_OWNER_OF", "P", "C", 10),
    edge("e3", "BENEFICIAL_OWNER_OF", "P", "A", 60),
    edge("e4", "BENEFICIAL_OWNER_OF", "A", "T", 70),
    edge("e5", "BENEFICIAL_OWNER_OF", "K", "T"),
  ],
};  // prettier-ignore

function serve(handler: (path: string, url: URL) => Response | null = () => null) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (raw: string) => {
      const url = new URL(raw);
      const path = url.pathname.replace("/v1/investigations/c1/", "");
      calls.push(`${path}${url.search}`);
      const answered = handler(path, url);
      if (answered) return answered;
      if (path === "suggest") return json(200, { nodes: [VIEW.nodes[0]], more: false });
      if (path === "ownership/C") return json(200, VIEW);
      return json(404, {});
    }),
  );
  return calls;
}

async function traceCrescent(onCanvas = vi.fn()) {
  render(<OwnershipPlace apiBaseUrl="http://x" bearerToken="t" investigationId="c1" onCanvas={onCanvas} />);
  fireEvent.change(screen.getByLabelText("Organisation or account"), { target: { value: "Cresc" } });
  fireEvent.click(screen.getByRole("button", { name: "Find" }));
  fireEvent.click(await screen.findByRole("button", { name: "Trace Crescent Imports Ltd" }));
  await screen.findByRole("table", { name: "Every owner and controller" });
  return onCanvas;
}

describe("the Ownership place", () => {
  it("names the beneficial owners, each share, and the circle", async () => {
    serve();
    await traceCrescent();
    expect(screen.getByText(/Beneficial owners at 25%: Elena Petrov \(47.8%\)/)).toBeTruthy();
    expect(screen.getByText("at least 0%")).toBeTruthy();
    expect(screen.getByText(/A circle of cross-holdings: Aegean Fiduciary Trust, Tamarind Holdings Ltd/)).toBeTruthy();
  });

  it("lists a party's chains in words, share by share", async () => {
    serve();
    await traceCrescent();
    fireEvent.click(screen.getByRole("button", { name: "Chains from Elena Petrov" }));
    expect(
      screen.getByText(
        "Elena Petrov → Aegean Fiduciary Trust (60%) → Tamarind Holdings Ltd (70%) → Crescent Imports Ltd (90%) = 37.8%",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Chains from Kestrel Nominees Ltd" }));
    expect(screen.getByText(/Tamarind Holdings Ltd \(share not stated\).* — share unknown/)).toBeTruthy();
  });

  it("asks the server at the chosen threshold, and refuses one out of range", async () => {
    const calls = serve();
    await traceCrescent();
    fireEvent.change(screen.getByLabelText("Beneficial ownership threshold"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Trace again" }));
    await waitFor(() => expect(calls).toContain("ownership/C?threshold=10"));
    fireEvent.change(screen.getByLabelText("Beneficial ownership threshold"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Trace again" }));
    expect(await screen.findByText("The threshold is a percentage above 0 and at most 100.")).toBeTruthy();
  });

  it("says why a structure is not traced", async () => {
    serve((path) =>
      path === "ownership/C" ? json(409, { error: "ownership_too_complex", detail: "owners reach this entity through more than 10 layers" }) : null,
    );
    render(<OwnershipPlace apiBaseUrl="http://x" bearerToken="t" investigationId="c1" onCanvas={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Organisation or account"), { target: { value: "Cresc" } });
    fireEvent.click(screen.getByRole("button", { name: "Find" }));
    fireEvent.click(await screen.findByRole("button", { name: "Trace Crescent Imports Ltd" }));
    expect(await screen.findByText("This structure is not traced: owners reach this entity through more than 10 layers.")).toBeTruthy();
  });

  it("puts the structure on the canvas and hands over its nodes", async () => {
    serve((path) => (path === "ownership/C/canvas" ? json(200, { delta: { seq: 1, op: "add", nodes: [], edges: [] }, added_nodes: 5, added_links: 5 }) : null));
    const onCanvas = await traceCrescent();
    fireEvent.click(screen.getByRole("button", { name: "Show the structure on the canvas" }));
    await waitFor(() => expect(onCanvas).toHaveBeenCalled());
    expect(onCanvas.mock.calls[0]?.[1]).toEqual(["C", "T", "A", "P", "K"]);
  });
});
