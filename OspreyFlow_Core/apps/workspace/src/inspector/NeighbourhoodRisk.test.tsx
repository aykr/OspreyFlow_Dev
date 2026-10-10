// @vitest-environment jsdom
// ADR-109 phase E: the Inspector's Neighbourhood risk part asks only when asked, names each
// contribution with its distance and alerts, and says why a neighbourhood is not scored.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import { NeighbourhoodRisk } from "./NeighbourhoodRisk";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const NODE = { id: "a", type: "Person", properties: { family_name: "Lay" } } as unknown as Node;

function part() {
  render(<NeighbourhoodRisk apiBaseUrl="http://x" bearerToken="t" investigationId="c1" node={NODE} />);
}

describe("Neighbourhood risk", () => {
  it("asks nothing until asked, then names each contribution", async () => {
    const fetched = vi.fn(async () =>
      new Response(JSON.stringify({
        node_id: "a", score: 0.75, max_hops: 2, decay: 0.5, window_days: 90, as_of: "2026-10-10",
        contributions: [{ node_id: "b", name: "Skilling", hops: 1, alert_ids: ["x"], summaries: ["Structuring"], contribution: 0.5 },
                        { node_id: "c", name: "Fastow", hops: 2, alert_ids: ["y"], summaries: [], contribution: 0.25 }],
      }), { status: 200 }));  // prettier-ignore
    vi.stubGlobal("fetch", fetched);
    part();
    expect(fetched).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Score this neighbourhood" }));
    expect(await screen.findByText(/Neighbourhood risk 0.75/)).toBeTruthy();
    expect(screen.getByText("Skilling, one hop away: 1 alert(s), +0.5 — Structuring")).toBeTruthy();
    expect(screen.getByText("Fastow, 2 hops away: 1 alert(s), +0.25")).toBeTruthy();
  });

  it("says why a neighbourhood is not scored", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ error: "neighbourhood_too_large", detail: "more than 5,000 entities lie within 2 hops; the neighbourhood is not scored in part" }), { status: 409 })));  // prettier-ignore
    part();
    fireEvent.click(screen.getByRole("button", { name: "Score this neighbourhood" }));
    expect(await screen.findByText(/Not scored: more than 5,000 entities lie within 2 hops/)).toBeTruthy();
  });
});
