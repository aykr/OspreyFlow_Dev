// @vitest-environment jsdom
// ADR-114 Amendment 5 point 9: Start — after signing in, a tile for each place the person may go: the
// Glass, the Ingest Studio, the Admin area; and the Admin area opened with no case, with its way back.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminWithoutCase } from "./AdminWithoutCase";
import { StartPage } from "./StartPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("StartPage", () => {
  it("shows one tile per place and says where each goes", () => {
    const chose = vi.fn();
    render(<StartPage places={["glass", "ingest", "admin"]} onChoose={chose} account={null} />);
    expect(screen.getByRole("heading", { name: "Where to?" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^The Glass/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Ingest Studio/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Admin/ }));
    expect(chose.mock.calls.map(([place]) => place)).toEqual(["glass", "ingest", "admin"]);
    expect(screen.getByText(/no case needed/i)).toBeTruthy();
  });

  it("leaves out a place the person may not go", () => {
    render(<StartPage places={["glass", "ingest"]} onChoose={() => undefined} account={null} />);
    expect(screen.queryByRole("button", { name: /^Admin/ })).toBeNull();
  });
});

describe("AdminWithoutCase", () => {
  it("opens the Admin area with no case, and goes back to Start", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    const start = vi.fn();
    render(
      <AdminWithoutCase apiBaseUrl="http://api" bearerToken="t" rights={new Set(["manage_people"])} onStart={start} account={null} />,
    );
    expect(screen.getByRole("tab", { name: "People and roles" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(start).toHaveBeenCalledTimes(1);
  });
});
