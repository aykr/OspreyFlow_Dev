// @vitest-environment jsdom
// ADR-143 decision 10 (L3.4): the Studio's Analyst promotions. What would fail if each part were
// wrong: a reviewer offered Approve on their own promotion, or a reviewer not told why they cannot
// decide (ADR-145 Amendment 4 decision 12); a rejection sent with no reason; Approve offered when an
// item is withheld from the reviewer (rule 3); the revert command shown to someone without
// `revert_loads`, or offered as a button (ADR-127 Amendment 9); the removed cases' layers drawn for
// someone who is not one of the dataset's Authors; a merge sheet closed without its grant cancelled.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Promotion } from "../../boards/promotionsApi";
import { AnalystPromotions, promotionRevertCommand } from "./promotions";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const P = (over: Partial<Promotion>): Promotion => ({
  id: "p1", load_id: "promotion-1", trigger: "analyst_promotion", dataset_id: "src", dataset_name: "Prison intel",
  case_id: "k", case_name: "Wing B", board_id: null, proposed_by: "alice", proposed_by_name: "A. Field",
  proposed_at: "2026-11-08T09:00:00Z", status: "awaiting_review", nodes: 2, links: 1, left_out: [],
  may_review: true, why_not: null, revert_command: null, ...over,
});  // prettier-ignore

type Routes = Record<string, (init?: RequestInit) => { status: number; body: unknown }>;

function serve(routes: Routes) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
    const hit = routes[key] ?? (() => ({ status: 404, body: { error: "not_found" } }));
    const { status, body } = hit(init);
    return new Response(status === 204 ? null : JSON.stringify(body), { status });
  });
  return calls;
}

function show(canRevert = false) {
  render(<AnalystPromotions apiBaseUrl="http://api" bearerToken="t" datasetId="src" canRevert={canRevert} username="dana" />);
}

const DETAILS = (p: Promotion, withheld = false) => ({
  status: 200,
  body: { promotion: p, withheld, items: [{ element_id: "n1", kind: "node", type: "Person", label: "Unknown male “Tall”", marking: "OFFICIAL", grading: "B21", source_note: "Wing report" }] },
});

describe("Analyst promotions", () => {
  it("lists each promotion, and an approver reviews and approves one", async () => {
    const p = P({});
    const calls = serve({
      "GET /v1/datasets/src/promotions": () => ({ status: 200, body: { promotions: [p] } }),
      "GET /v1/datasets/src/promotions/p1": () => DETAILS(p),
      "POST /v1/datasets/src/promotions/p1/decision": () => ({ status: 200, body: P({ status: "committed" }) }),
    });
    show();
    expect(await screen.findByText("promotion-1")).toBeTruthy();
    expect(screen.getByText("2 items and 1 link")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Review/ }));
    expect(await screen.findByText("Unknown male “Tall”")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve and commit" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/decision"))).toBe(true));
    const sent = calls.find((c) => c.url.endsWith("/decision"))!;
    expect(JSON.parse(String(sent.init?.body))).toEqual({ approve: true });
  });

  it("says why one who may not decide cannot, and offers them no decision", async () => {
    const p = P({ may_review: false, why_not: "You sent this promotion: a second person must review it." });
    serve({
      "GET /v1/datasets/src/promotions": () => ({ status: 200, body: { promotions: [p] } }),
      "GET /v1/datasets/src/promotions/p1": () => DETAILS(p),
    });
    show();
    expect(await screen.findByText(/a second person must review it/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Details/ }));
    await screen.findByText("Unknown male “Tall”");
    expect(screen.queryByRole("button", { name: "Approve and commit" })).toBeNull();
  });

  it("offers no approval when an item is withheld from the reviewer", async () => {
    const p = P({});
    serve({
      "GET /v1/datasets/src/promotions": () => ({ status: 200, body: { promotions: [p] } }),
      "GET /v1/datasets/src/promotions/p1": () => DETAILS(p, true),
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: /Review/ }));
    expect(await screen.findByText(/not shown to you/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Approve and commit" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("needs a reason to reject, and sends it", async () => {
    const p = P({});
    const calls = serve({
      "GET /v1/datasets/src/promotions": () => ({ status: 200, body: { promotions: [p] } }),
      "GET /v1/datasets/src/promotions/p1": () => DETAILS(p),
      "POST /v1/datasets/src/promotions/p1/decision": () => ({ status: 200, body: P({ status: "rejected", reason: "Too thin" }) }),
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: /Review/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Reject with a reason" }));
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(await screen.findByText(/Say why it is rejected/)).toBeTruthy();
    expect(calls.some((c) => c.url.endsWith("/decision"))).toBe(false);
    fireEvent.change(screen.getByLabelText("Why it is rejected"), { target: { value: "Too thin" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/decision"))).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith("/decision"))!.init?.body))).toEqual({ approve: false, reason: "Too thin" });
  });

  it("shows the revert command only to a holder of revert_loads, as text, never a button", async () => {
    const p = P({ status: "committed", may_review: false, revert_command: "x" });
    serve({ "GET /v1/datasets/src/promotions": () => ({ status: 200, body: { promotions: [p] } }) });
    show(false);
    await screen.findByText("promotion-1");
    expect(screen.queryByText(promotionRevertCommand("promotion-1", "dana"))).toBeNull();
    cleanup();
    show(true);
    expect(await screen.findByText(promotionRevertCommand("promotion-1", "dana"))).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Revert/ })).toBeNull();
  });

  it("says who has Review promotions when the reader does not", async () => {
    serve({ "GET /v1/datasets/src/promotions": () => ({ status: 403, body: { detail: { error: "right_required" } } }) });
    show();
    expect(await screen.findByText(/You need Review promotions/)).toBeTruthy();
  });

  it("draws the removed cases' layers for an Author, and cancels a merge's grant when it is closed", async () => {
    const calls = serve({
      "GET /v1/datasets/src/promotions": () => ({ status: 200, body: { promotions: [] } }),
      "GET /v1/datasets/src/removed-cases": () => ({ status: 200, body: { dataset_id: "src", cases: [{ investigation_id: "k", name: "Wing B", items: 2, mergeable: true }] } }),
      "POST /v1/datasets/src/removed-cases/k/merge-sheet": () => ({
        status: 200,
        body: { grant_id: "g1", investigation_id: "k", case_name: "Wing B", dataset_id: "src", dataset_name: "Prison intel", highest_marking: "OFFICIAL",
          policy: "author_promotes", items: [{ item_id: "i1", element_id: "n1", kind: "node", type: "Person", label: "Tall", marking: "OFFICIAL", problems: [] }],
          checks: [], warnings: [], recorded_as: "One load." },
      }),  // prettier-ignore
      "DELETE /v1/datasets/src/layer-merges/g1": () => ({ status: 204, body: null }),
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: /Merge into the dataset/ }));
    expect(await screen.findByText(/for this merge alone/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "DELETE" && c.url.endsWith("/layer-merges/g1"))).toBe(true));
  });

  it("draws no removed cases' layers for someone who is not an Author", async () => {
    serve({
      "GET /v1/datasets/src/promotions": () => ({ status: 200, body: { promotions: [] } }),
      "GET /v1/datasets/src/removed-cases": () => ({ status: 403, body: { error: "not_an_author", detail: "Only one of the dataset's Authors…" } }),
    });
    show();
    await screen.findByText(/No analyst promotion/);
    expect(screen.queryByText(/Removed cases/)).toBeNull();
  });

  it("shows a drawn merge's matches to its reviewer before they approve (L3.9)", async () => {
    const p = P({ trigger: "drawn_merge", case_name: "Night visits" });
    serve({
      "GET /v1/datasets/src/promotions": () => ({ status: 200, body: { promotions: [p] } }),
      "GET /v1/datasets/src/promotions/p1": () => ({
        status: 200,
        body: { ...DETAILS(p).body, matches: [{ drawn: "e1", drawn_label: "Mercer", loaded: "p-loaded", loaded_label: "Mercer", loaded_type: "Person", score: 1, why: "chosen at the merge" }] },
      }),
    });
    show();
    await screen.findByText("promotion-1");
    fireEvent.click(screen.getByRole("button", { name: /Review/ }));
    const list = await screen.findByRole("list", { name: "Proposed matches" });
    expect(list.textContent).toBe("Mercer and Mercer (Person), 100%");
  });
});
