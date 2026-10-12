// @vitest-environment jsdom
// ADR-111 Amendment 3: Superset dashboards inside the Glass. The Conduit decides who may open a
// board; these prove the Glass asks for the list and a token, mounts exactly the board the Conduit
// named at the origin it named, fetches each later token from the Conduit too, and says a refusal.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { applyTheme } from "../theme/theme";
import { EmbeddedDashboards, type Embed } from "./EmbeddedDashboards";
import { ReportsPlace } from "./ReportsPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const BOARDS = [
  { slug: "compliance-board", title: "Compliance board" },
  { slug: "fraud-board", title: "Fraud board" },
];

function serve(list: () => Response, token: (slug: string) => Response) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.replace("http://api", "");
      calls.push(`${init?.method ?? "GET"} ${path}`);
      if (path === "/v1/reports/dashboards") return list();
      const m = /^\/v1\/reports\/dashboards\/([^/]+)\/guest-token$/.exec(path);
      if (m) return token(decodeURIComponent(m[1]!));
      return json(200, {});
    }),
  );
  return calls;
}

let issued = 0;
// Each token differs, so a test can tell a fresh token from one reused past its five minutes.
const granted = (slug: string) =>
  json(200, { token: `t-${slug}-${++issued}`, uuid: `uuid-${slug}`, superset_origin: "http://bi.example" });

describe("Superset dashboards in the Glass", () => {
  it("mounts the first board the Conduit lists, at the origin it names, and asks the Conduit for each later token", async () => {
    serve(() => json(200, BOARDS), granted);
    const embed = vi.fn<Embed>(async () => ({}));
    render(<EmbeddedDashboards apiBaseUrl="http://api" bearerToken="t" embed={embed} />);
    await waitFor(() => expect(embed).toHaveBeenCalledTimes(1));
    const options = embed.mock.calls[0]![0];
    expect([options.id, options.supersetDomain]).toEqual(["uuid-compliance-board", "http://bi.example"]);
    const later = await options.fetchGuestToken();
    expect(later).toMatch(/^t-compliance-board-\d+$/);
    expect(await options.fetchGuestToken()).not.toBe(later); // each from the Conduit, never reused
  });

  it("opens another board when it is chosen", async () => {
    serve(() => json(200, BOARDS), granted);
    const embed = vi.fn<Embed>(async () => ({}));
    render(<EmbeddedDashboards apiBaseUrl="http://api" bearerToken="t" embed={embed} />);
    fireEvent.click(await screen.findByRole("button", { name: "Fraud board" }));
    await waitFor(() => expect(embed.mock.calls.at(-1)![0].id).toBe("uuid-fraud-board"));
  });

  // ADR-111 Amendment 4: a board is drawn in the Glass's own look, and only the Glass names it.
  it("opens a board in the Glass's current mode, hiding Superset's own title and chart menus", async () => {
    applyTheme("light");
    serve(() => json(200, BOARDS), granted);
    const embed = vi.fn<Embed>(async () => ({}));
    render(<EmbeddedDashboards apiBaseUrl="http://api" bearerToken="t" embed={embed} />);
    await waitFor(() => expect(embed).toHaveBeenCalledTimes(1));
    const ui = embed.mock.calls[0]![0].dashboardUiConfig!;
    expect(ui.urlParams?.themeMode).toBe("default");
    expect([ui.hideTitle, ui.hideChartControls]).toEqual([true, true]);
    applyTheme("dark");
  });

  it("follows the person switching between dark and light while a board is open", async () => {
    applyTheme("dark");
    serve(() => json(200, BOARDS), granted);
    const setThemeMode = vi.fn();
    const embed = vi.fn<Embed>(async () => ({ setThemeMode }));
    render(<EmbeddedDashboards apiBaseUrl="http://api" bearerToken="t" embed={embed} />);
    await waitFor(() => expect(embed).toHaveBeenCalledTimes(1));
    expect(embed.mock.calls[0]![0].dashboardUiConfig!.urlParams?.themeMode).toBe("dark");
    await waitFor(() => expect(setThemeMode).toHaveBeenCalledWith("dark"));
    applyTheme("light");
    await waitFor(() => expect(setThemeMode).toHaveBeenLastCalledWith("default"));
    applyTheme("dark");
    await waitFor(() => expect(setThemeMode).toHaveBeenLastCalledWith("dark"));
  });

  it("says when there is no board this person may open, and mounts nothing", async () => {
    serve(() => json(200, []), granted);
    const embed = vi.fn<Embed>(async () => ({}));
    render(<EmbeddedDashboards apiBaseUrl="http://api" bearerToken="t" embed={embed} />);
    expect(await screen.findByText(/No dashboard you may open/)).toBeTruthy();
    expect(embed).not.toHaveBeenCalled();
  });

  it("says a refused board in words, never mounting it", async () => {
    serve(() => json(200, BOARDS.slice(0, 1)), () => json(404, {}));
    const embed = vi.fn<Embed>(async () => ({}));
    render(<EmbeddedDashboards apiBaseUrl="http://api" bearerToken="t" embed={embed} />);
    expect((await screen.findByRole("alert")).textContent).toBe("That dashboard is not one you may open.");
    expect(embed).not.toHaveBeenCalled();
  });

  it("is the Reports view's second tab, beside the figures", async () => {
    serve(() => json(200, BOARDS), granted);
    const embed = vi.fn<Embed>(async () => ({}));
    render(<ReportsPlace apiBaseUrl="http://api" bearerToken="t" investigationId="c1" canDownload={false} embed={embed} />);
    expect(screen.getByRole("tab", { name: "Figures" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: "Dashboards" }));
    await waitFor(() => expect(embed).toHaveBeenCalled());
  });
});
