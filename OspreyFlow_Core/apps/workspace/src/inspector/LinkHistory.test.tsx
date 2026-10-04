// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkHistory } from "./LinkHistory";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stub(status: number, json: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: status === 200, status, json: async () => json })));
}

const props = { apiBaseUrl: "http://api.test", bearerToken: "tok", investigationId: "inv-1", edgeId: "e2" };

const change = {
  id: "c1",
  investigation_id: "inv-1",
  edge_id: "e2",
  previous_edge_id: "e1",
  changed_by: "analyst-1",
  changed_at: "2026-10-01T09:00:00Z",
  reason: "Told so by the witness",
  before: { type: "ASSOCIATE_OF", properties: {}, interval: null, occurrences: 3 },
  after: { type: "FAMILY_OF", properties: { relation: "cousin" }, interval: null, occurrences: 3 },
};

describe("LinkHistory", () => {
  it("lists each change with who, why and what moved, newest first", async () => {
    stub(200, { changes: [change], truncated: false });
    render(<LinkHistory {...props} />);
    await waitFor(() => expect(screen.getByText("Told so by the witness")).toBeTruthy());
    expect(screen.getByText("Type: Associate of → Family of")).toBeTruthy();
    expect(screen.getByText("relation: (none) → cousin")).toBeTruthy();
    expect(screen.getByText(/analyst-1/)).toBeTruthy();
  });

  it("says so when the link has never been changed", async () => {
    stub(200, { changes: [], truncated: false });
    render(<LinkHistory {...props} />);
    await waitFor(() => expect(screen.getByText(/has not been changed/)).toBeTruthy());
  });

  it("says when older changes are not shown", async () => {
    stub(200, { changes: [change], truncated: true });
    render(<LinkHistory {...props} />);
    await waitFor(() => expect(screen.getByText(/Older changes are not shown/)).toBeTruthy());
  });

  it("answers a link the person cannot see as a link that is not in their view", async () => {
    stub(404, { error: "link_not_found" });
    render(<LinkHistory {...props} />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("not in your view"));
  });
});
