// @vitest-environment jsdom
// ADR-044 Amendment 1: a stopped watch says why, in the Conduit's words, beside Stopped; an active one
// shows no reason.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MonitorPanel } from "./MonitorPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const WHY = "Its saved pattern is no longer its owner's.";

function serve(monitors: Record<string, unknown>[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = String(url).endsWith("/monitors") ? { monitors } : { patterns: [] };
      return { ok: true, status: 200, json: async () => body } as Response;
    }),
  );
}

const watch = (extra: Record<string, unknown>) => ({
  id: "m1", pattern_id: "p1", owner_id: "a1", status: "active", created_at: "2026-11-14T09:00:00Z",
  every: "daily", hour: 6, ...extra,
});  // prettier-ignore

describe("a watch in the list", () => {
  it("shows why it is stopped", async () => {
    serve([watch({ status: "stopped", status_detail: "pattern_gone", stopped_why: WHY })]);
    render(<MonitorPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    expect(await screen.findByText(WHY)).toBeTruthy();
  });

  it("shows no reason while active", async () => {
    serve([watch({ stopped_why: WHY })]);
    render(<MonitorPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    expect(await screen.findByText("Active")).toBeTruthy();
    expect(screen.queryByText(WHY)).toBeNull();
  });
  // ADR-044 Amendment 2: active, with loads in a row that could not check its owner's sign-in.
  it("shows a stopped one's reason, never an active note left with it", async () => {
    const why = "Its owner's sign-in could not be checked at three loads in a row. It is tried again at the next.";
    const note = "Its owner's sign-in could not be checked at the last two loads. It stops if the next is the third in a row.";
    serve([watch({ status: "stopped", status_detail: "unreachable", stopped_why: why, unreachable_in_a_row: 0, status_note: note })]);
    render(<MonitorPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    expect(await screen.findByText(why)).toBeTruthy();
    expect(screen.queryByText(note)).toBeNull();
  });

  it("says, while active, how many loads could not check its owner's sign-in", async () => {
    const note = "Its owner's sign-in could not be checked at the last two loads. It stops if the next is the third in a row.";
    serve([watch({ unreachable_in_a_row: 2, status_note: note })]);
    render(<MonitorPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    expect(await screen.findByText(note)).toBeTruthy();
  });
});
