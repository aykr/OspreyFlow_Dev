// @vitest-environment jsdom
// ADR-114 Amendment 5 point 9: Start — after signing in, a tile for each place the person may go: the
// Glass, the Ingest Studio, the Admin area; and the Admin area opened with no case, with its way back.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminWithoutCase } from "./AdminWithoutCase";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminWithoutCase", () => {
  it("opens the Admin area with no case, and goes back to Start", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    const start = vi.fn();
    render(
      <AdminWithoutCase apiBaseUrl="http://api" bearerToken="t" rights={new Set(["manage_people"])} onStart={start} account={null} marking={null} />,
    );
    expect(screen.getByRole("tab", { name: "People and roles" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(start).toHaveBeenCalledTimes(1);
  });
});
