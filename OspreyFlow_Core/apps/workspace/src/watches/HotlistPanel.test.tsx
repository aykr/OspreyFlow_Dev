// @vitest-environment jsdom
// ADR-127 decision 7(b): a hotlist's identifier is stored in its canonical form, so a number typed
// `07700 900310` is kept as `+447700900310` and matched on that. The analyst sees what they typed:
// the list shows the typed form, and the canonical one only for a row whose typed form is not known.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HotlistPanel } from "./HotlistPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve(hotlists: Record<string, unknown>[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ hotlists }) }) as Response),
  );
}

const row = (extra: Record<string, unknown>) => ({
  id: "h1",
  identifier: "+447700900310",
  owner_id: "a1",
  review_date: "2027-01-01",
  status: "active",
  created_at: "2026-10-26T09:00:00Z",
  ...extra,
});

describe("the hotlist list", () => {
  it("shows the form the analyst typed, not the canonical one it is matched on", async () => {
    serve([row({ identifier_typed: "07700 900310" })]);
    render(<HotlistPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    expect(await screen.findByText("07700 900310")).toBeTruthy();
    expect(screen.queryByText("+447700900310")).toBeNull();
  });

  it("shows the stored identifier for a row with no typed form", async () => {
    serve([row({ identifier_typed: null })]);
    render(<HotlistPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    expect(await screen.findByText("+447700900310")).toBeTruthy();
  });

  it("says, for a row kept as written, that it matches only that exact text", async () => {
    serve([row({ identifier: "+44-odd", identifier_typed: "+44-odd", identifier_canonical: false })]);
    render(<HotlistPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    expect(await screen.findByText("kept as written: matches only this exact text")).toBeTruthy();
  });

  it("says nothing of the kind for a canonicalised row, or one not yet read", async () => {
    serve([
      row({ id: "h1", identifier_typed: "07700 900310", identifier_canonical: true }),
      row({ id: "h2", identifier: "+447700900311", identifier_typed: null, identifier_canonical: null }),
    ]);
    render(<HotlistPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" />);
    await screen.findByText("07700 900310");
    expect(screen.queryByText(/kept as written/)).toBeNull();
  });
});
