// @vitest-environment jsdom
// Admin › Policies › Grading scheme (ADR-145 decision 12, ADR-143 decision 11 and Amendment 6; L2.7).
// Red if the section shows without administer_system, if it shows any grade but the Conduit's, offers
// any way to change the scheme from the page, or says a failed read as no scheme.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "../AdminPlace";
import { GRADING_COMMAND } from "./GradingScheme";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SCHEME = { scheme: "admiralty", source: ["A", "B", "C", "D", "E", "F"], intelligence: ["1", "2", "3", "4", "5", "6"],
                 handling: ["P", "C"] }; // prettier-ignore

function serve(status = 200) {
  const asked: { method: string; path: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      asked.push({ method: init?.method ?? "GET", path });
      if (path === "/v1/grading-scheme") return new Response(JSON.stringify(SCHEME), { status });
      return new Response("[]", { status: 200 });
    }),
  );
  return asked;
}

function open(rights: string[]) {
  render(<AdminPlace apiBaseUrl="http://api" bearerToken="t" rights={new Set(rights)} />);
  const nav = screen.getByRole("navigation", { name: "Admin sections" });
  fireEvent.click(within(nav).getByRole("button", { name: "Grading scheme" }));
}

describe("Grading scheme", () => {
  it("is a section for administer_system alone", () => {
    serve();
    render(<AdminPlace apiBaseUrl="http://api" bearerToken="t" rights={new Set(["operate_schedules", "manage_people"])} />);
    expect(screen.queryByRole("button", { name: "Grading scheme" })).toBeNull();
  });

  it("shows the Conduit's scheme and each part's grades in order, read-only, and changes nothing", async () => {
    const asked = serve();
    open(["administer_system"]);
    const table = await screen.findByRole("table", { name: "The grades of admiralty" });
    const rows = within(table).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual(["SourceA, B, C, D, E, F", "Intelligence1, 2, 3, 4, 5, 6", "HandlingP, C"]);
    const section = screen.getByRole("region", { name: "Changing the grading scheme" });
    expect(within(section).getByText(GRADING_COMMAND)).toBeTruthy();
    expect(screen.queryAllByRole("combobox")).toEqual([]);
    expect(screen.queryAllByRole("textbox")).toEqual([]);
    expect(asked.filter((a) => a.method !== "GET")).toEqual([]);
  });

  it("copies the dry run's command", async () => {
    serve();
    const writeText = vi.fn(async () => undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    open(["administer_system"]);
    fireEvent.click(await screen.findByRole("button", { name: "Copy the grading change command" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(GRADING_COMMAND));
    expect(GRADING_COMMAND).toContain("--dry-run");
    expect((await screen.findByRole("status")).textContent).toMatch(/the dry run first/);
  });

  it("says a failed read, never an empty scheme", async () => {
    serve(503);
    open(["administer_system"]);
    expect((await screen.findByRole("alert")).textContent).toBe("The grading scheme could not be read (503).");
    expect(screen.queryByRole("table")).toBeNull();
  });
});
