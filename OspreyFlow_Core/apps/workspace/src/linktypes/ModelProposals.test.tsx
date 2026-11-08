// @vitest-environment jsdom
// The Studio's Model tab's proposals block (ADR-143 decision 9; L3.5): what a data engineer of the
// dataset is shown (never the case a type was proposed in), the two decisions each with a reason,
// the Conduit's refusal in its own words, and nothing at all for a person the routes refuse.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModelProposals } from "./ModelProposals";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PENDING = {
  id: "p1",
  name: "BRIBED",
  label: "Bribed",
  from_types: ["Person"],
  to_types: ["Person"],
  directed: true,
  proposed_by: "alice",
  proposed_at: "2026-11-08T10:00:00Z",
  reason: "Paid a prison officer to carry items in",
  status: "pending",
};
const DECLINED = { ...PENDING, id: "p2", name: "SEEN_NEAR", label: "Seen near", reason: "Near the gate at visiting time", proposed_by: "bob", status: "rejected", decided_by: "dan", decision_reason: "Use PRESENT_AT" };

type Reply = { status: number; json: unknown };

function serve(...replies: Reply[]) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const reply = replies.shift() ?? { status: 200, json: { proposals: [] } };
      return { ok: reply.status === 200, status: reply.status, json: async () => reply.json };
    }),
  );
  return calls;
}

function mount() {
  return render(<ModelProposals apiBaseUrl="http://api.test" bearerToken="tok" datasetId="ds-1" datasetName="Prison (synthetic)" />);
}

describe("ModelProposals", () => {
  it("lists the dataset's proposals with what each means and who proposed it, and names no case", async () => {
    const calls = serve({ status: 200, json: { proposals: [PENDING, DECLINED] } });
    mount();
    expect(await screen.findByText("Bribed")).toBeTruthy();
    expect(calls[0]!.url).toBe("http://api.test/v1/datasets/ds-1/model/proposals");
    expect(screen.getByText(/What it means: “Paid a prison officer/)).toBeTruthy();
    expect(screen.getByText(/Person to Person, one way\. Proposed by alice on 2026-11-08\./)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Proposed link types (1 to decide)" })).toBeTruthy();
    expect(screen.getByText("Declined")).toBeTruthy();
    expect(screen.getByText(/Decided by dan: “Use PRESENT_AT”/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add Bribed to the draft model…" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Decline Seen near…" })).toBeNull();
    expect(document.body.textContent).not.toMatch(/inv-|case \w+-\d/);
  });

  it("adds a type to the draft model with a reason, then reads the list again", async () => {
    const calls = serve(
      { status: 200, json: { proposals: [PENDING] } },
      { status: 200, json: { ...PENDING, status: "accepted" } },
      { status: 200, json: { proposals: [{ ...PENDING, status: "accepted", in_model: "draft" }] } },
    );
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Add Bribed to the draft model…" }));
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: "Seen in three cases" } });
    fireEvent.click(screen.getByRole("button", { name: "Add to the draft model" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Say what stands behind its links: Direct or Probabilistic.");
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: " " } });
    fireEvent.click(screen.getByLabelText(/^Direct/));
    fireEvent.click(screen.getByRole("button", { name: "Add to the draft model" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Say why: a reason is required.");
    expect(calls).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: "Seen in three cases" } });
    fireEvent.click(screen.getByRole("button", { name: "Add to the draft model" }));
    expect(await screen.findByRole("status")).toHaveProperty(
      "textContent",
      "Bribed added to the draft model: its links can be promoted once that version is made live.",
    );
    expect(calls[1]).toEqual({
      url: "http://api.test/v1/datasets/ds-1/model/proposals/p1/accept",
      method: "POST",
      body: { basis: "direct", reason: "Seen in three cases" },
    });
    await waitFor(() => expect(screen.getByText("In the draft model")).toBeTruthy());
  });

  it("declines with a reason, and shows the Conduit's refusal in its own words", async () => {
    const calls = serve(
      { status: 200, json: { proposals: [PENDING] } },
      { status: 422, json: { error: "proposal_refused", detail: "You proposed this type, so another data engineer of the dataset decides it." } },
    );
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Decline Bribed…" }));
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: "Use PAID" } });
    fireEvent.click(screen.getByRole("button", { name: "Decline" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "You proposed this type, so another data engineer of the dataset decides it.",
    );
    expect(calls[1]!.url).toBe("http://api.test/v1/datasets/ds-1/model/proposals/p1/decline");
  });

  it("is not drawn at all for a person without the right, or outside the dataset", async () => {
    for (const status of [403, 404]) {
      serve({ status, json: { error: "x" } });
      const { container } = mount();
      await waitFor(() => expect(container.innerHTML).toBe(""));
      cleanup();
    }
  });

  it("says when the list could not be read rather than showing none", async () => {
    serve({ status: 500, json: {} });
    mount();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The proposed link types could not be read. Open the tab again to retry.");
    expect(screen.queryByText("No link types have been proposed for this dataset.")).toBeNull();
  });

  it("offers an accepted type lost from the model to be added again, and says the model's refusal in its words", async () => {
    const calls = serve(
      { status: 200, json: { proposals: [{ ...PENDING, status: "accepted", in_model: null, decided_by: "dan", decision_reason: "Useful" }] } },
      { status: 409, json: { error: "model_refused", detail: "this dataset already has a draft, version 4: save or discard it first" } },
    );
    mount();
    expect(await screen.findByText("Accepted, not in the model")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Proposed link types (1 to decide)" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Decline Bribed…" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Add Bribed to the draft model again…" }));
    fireEvent.click(screen.getByLabelText(/^Probabilistic/));
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: "Lost with the draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Add to the draft model" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "this dataset already has a draft, version 4: save or discard it first");
    expect(calls[1]!.body).toEqual({ basis: "probabilistic", reason: "Lost with the draft" });
  });

  it("tags an accepted type live once its version is", async () => {
    serve({ status: 200, json: { proposals: [{ ...PENDING, status: "accepted", in_model: "live" }] } });
    mount();
    expect(await screen.findByText("In the live model")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Bribed/ })).toBeNull();
  });
});
