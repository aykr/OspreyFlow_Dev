// @vitest-environment jsdom
//
// The guided install page's shell: the nav shows the chosen mode's screens only, in decision 6's
// order, and the Map screen is the Set-up console's Geospatial one.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  getConfig: vi.fn(),
  putConfig: vi.fn(),
  getInstallState: vi.fn(),
  putInstallAnswers: vi.fn(),
  getInstallDoctor: vi.fn(),
  streamInstall: vi.fn(),
}));
vi.mock("./api/client", async (original) => ({
  ...(await original<typeof import("./api/client")>()),
  ...client,
}));

import { InstallApp } from "./InstallApp";
import { INSTALL_SCREENS, installNav } from "./store";

const MODES = {
  lite: { available: true },
  small: { available: false, says: "The small install arrives with stage B6. Your answers are saved for it." },
  enterprise: { available: false, says: "The enterprise install arrives with stage B7. Your answers are saved for it." },
};

function navNames(): string[] {
  return screen
    .getByRole("navigation", { name: "Install screens" })
    .querySelectorAll("button")
    .length
    ? [...screen.getByRole("navigation", { name: "Install screens" }).querySelectorAll("button")].map((b) => b.textContent ?? "")
    : [];
}

beforeEach(() => {
  client.getConfig.mockReset().mockResolvedValue({ profile: "local-lite" });
  client.getInstallState.mockReset();
  client.putConfig.mockReset();
  client.putInstallAnswers.mockReset();
});
afterEach(cleanup);

describe("the screen lists", () => {
  it("follow decision 6 for each mode", () => {
    expect(INSTALL_SCREENS.lite).toEqual([
      "Mode", "Folders", "Profile", "Components", "Map", "Models", "Governance", "Demo packs", "Review", "Installing",
    ]);
    expect(INSTALL_SCREENS.small).toEqual([
      "Mode", "Cloud and region", "Domain", "Components", "Models", "Governance", "Demo packs", "Review",
    ]);
    expect(INSTALL_SCREENS.enterprise).toEqual(INSTALL_SCREENS.small);
    expect(INSTALL_SCREENS.lite).not.toContain("Preflight");
  });

  it("never offer Installing as a place to go, only as where Install leads", () => {
    expect(installNav("lite")).not.toContain("Installing");
    expect(installNav("lite")).toContain("Review");
  });
});

describe("InstallApp", () => {
  it("shows Lite's screens only for Lite", async () => {
    client.getInstallState.mockResolvedValue({ mode: "lite", answers: { mode: "lite" }, packs: [], modes: MODES, home: "/home/ada" });
    render(<InstallApp />);
    await waitFor(() => expect(navNames().length).toBeGreaterThan(0));
    expect(navNames()).toEqual(["Mode", "Folders", "Profile", "Components", "Map", "Models", "Governance", "Demo packs", "Review"]);
  });

  it("shows Small's screens only for Small", async () => {
    client.getInstallState.mockResolvedValue({ mode: "small", answers: { mode: "small" }, packs: [], modes: MODES, home: "/home/ada" });
    render(<InstallApp />);
    await waitFor(() => expect(navNames().length).toBeGreaterThan(0));
    expect(navNames()).toEqual(["Mode", "Cloud and region", "Domain", "Components", "Models", "Governance", "Demo packs", "Review"]);
    expect(screen.queryByRole("button", { name: "Folders" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Map" })).toBeNull();
  });
});
