// @vitest-environment jsdom
//
// 9 October 2026: a refused history route (404 for a case this account cannot open) would have set
// the error body as the list of steps, and rendering it would have thrown. A refusal is an empty
// history, not a crash.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { HistoryPanel } from "./HistoryPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows an empty history when the route refuses", async () => {
  vi.stubGlobal(
    "fetch",
    async () => new Response(JSON.stringify({ error: "investigation_not_found" }), { status: 404 }),
  );
  render(
    <HistoryPanel
      open
      onClose={() => undefined}
      investigationId="inv-1"
      apiBaseUrl="http://test.invalid"
      bearerToken="unused"
      onRestored={() => undefined}
    />,
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.getByRole("dialog")).toBeTruthy();
});
