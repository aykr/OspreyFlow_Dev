// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProposedTypes } from "./ProposedTypes";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PENDING = {
  id: "p1",
  name: "KNOWN_TO",
  label: "Known to",
  from_types: ["Person"],
  to_types: ["Person"],
  directed: false,
  investigation_id: "inv-1",
  owning_unit: "unit-1",
  proposed_by: "analyst-1",
  proposed_at: "2026-10-05T10:00:00Z",
  reason: "They know each other by sight",
  status: "pending",
};
const PROMOTED = { ...PENDING, id: "p2", name: "SEEN_WITH", label: "Seen with", reason: "Often together", status: "promoted", promoted_name: "SEEN_WITH", basis: "probabilistic" };

type Reply = { status: number; json: unknown };

/** Answers each request in turn, recording what was asked. */
function serve(...replies: Reply[]) {
  const calls: { url: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const reply = replies.shift() ?? { status: 200, json: { proposals: [] } };
    return { ok: reply.status === 200, status: reply.status, json: async () => reply.json };
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function mount(onDecided = vi.fn()) {
  render(<ProposedTypes apiBaseUrl="http://api.test" bearerToken="tok" open onClose={vi.fn()} onDecided={onDecided} />);
  return onDecided;
}

describe("ProposedTypes", () => {
  it("lists the unit's proposals with what each would be and why it was proposed", async () => {
    serve({ status: 200, json: { proposals: [PENDING, PROMOTED] } });
    mount();
    expect(await screen.findByText("Known to")).toBeTruthy();
    expect(screen.getByText(/KNOWN_TO · Person and Person, either way/)).toBeTruthy();
    expect(screen.getByText(/They know each other by sight/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Promote Known to…" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retire Seen with…" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Promote Seen with…" })).toBeNull();
  });

  it("promotes with the basis chosen and a reason, then reads the list again", async () => {
    const calls = serve(
      { status: 200, json: { proposals: [PENDING] } },
      { status: 200, json: { ...PENDING, status: "promoted" } },
      { status: 200, json: { proposals: [{ ...PENDING, status: "promoted" }] } },
    );
    const onDecided = mount();
    fireEvent.click(await screen.findByRole("button", { name: "Promote Known to…" }));
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: "A loader backs it" } });
    fireEvent.click(screen.getByRole("button", { name: "Promote" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Direct or Probabilistic/);
    fireEvent.click(screen.getByLabelText(/^Direct/));
    fireEvent.click(screen.getByRole("button", { name: "Promote" }));
    await waitFor(() => expect(onDecided).toHaveBeenCalled());
    expect(calls[1]).toEqual({
      url: "http://api.test/v1/admin/link-types/p1/promote",
      body: { basis: "direct", reason: "A loader backs it" },
    });
    expect(calls).toHaveLength(3);
    expect((await screen.findByRole("status")).textContent).toContain("Known to promoted");
  });

  it("asks for a new name when the server says the name is taken, and sends it", async () => {
    const calls = serve(
      { status: 200, json: { proposals: [PENDING] } },
      { status: 422, json: { error: "proposal_refused", detail: "Its links do not all fit KNOWN_TO as promoted: promote it under a new name." } },
      { status: 200, json: { ...PENDING, status: "promoted" } },
    );
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Promote Known to…" }));
    fireEvent.click(screen.getByLabelText(/^Probabilistic/));
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: "Its own type" } });
    fireEvent.click(screen.getByRole("button", { name: "Promote" }));
    expect((await screen.findByRole("alert")).textContent).toContain("under a new name");
    fireEvent.change(screen.getByLabelText("Promote as (a new type ID)"), { target: { value: "knows_staff_at" } });
    fireEvent.click(screen.getByRole("button", { name: "Promote" }));
    await waitFor(() => expect(calls).toHaveLength(4));
    expect(calls[2]!.body).toEqual({ basis: "probabilistic", reason: "Its own type", rename_to: "KNOWS_STAFF_AT" });
  });

  it("rejects and retires with a reason, and sends nothing without one", async () => {
    const calls = serve(
      { status: 200, json: { proposals: [PENDING, PROMOTED] } },
      { status: 200, json: { ...PENDING, status: "rejected" } },
      { status: 200, json: { proposals: [PROMOTED] } },
      { status: 200, json: { proposals: [] } },
      { status: 200, json: { proposals: [] } },
    );
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Reject Known to…" }));
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Say why/);
    expect(calls).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: "Use ASSOCIATE_OF" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(calls).toHaveLength(3));
    expect(calls[1]!.url).toBe("http://api.test/v1/admin/link-types/p1/reject");
    fireEvent.click(await screen.findByRole("button", { name: "Retire Seen with…" }));
    fireEvent.change(screen.getByLabelText("Why? (required)"), { target: { value: "Superseded" } });
    fireEvent.click(screen.getByRole("button", { name: "Retire" }));
    await waitFor(() => expect(calls).toHaveLength(5));
    expect(calls[3]).toEqual({ url: "http://api.test/v1/admin/link-types/retire", body: { name: "SEEN_WITH", reason: "Superseded" } });
  });

  it("says when the list cannot be read, rather than showing an empty one", async () => {
    serve({ status: 500, json: {} });
    mount();
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not be read/);
    expect(screen.queryByText(/No proposals/)).toBeNull();
  });
});
