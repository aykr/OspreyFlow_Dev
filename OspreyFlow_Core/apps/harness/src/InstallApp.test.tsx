// @vitest-environment jsdom
//
// The guided install page's shell: the nav shows the chosen mode's screens only, in decision 6's
// order, and the Map screen is the Set-up console's Geospatial one.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  small: { available: false, says: "A small server is built from a terminal on this computer, from the answers you save here: ospreyflow install --mode small --cloud aws (or azure) --config .install/install.yaml" },
  enterprise: { available: false, says: "An enterprise install is built from a terminal on this computer, from the answers you save here: ospreyflow install --mode enterprise --cloud aws (or azure) --config .install/install.yaml" },
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

describe("the draft's profile and address (S11, the owner's ruling of 2 November 2026)", () => {
  const small = (answers: Record<string, unknown>) => ({ mode: "small", answers: { mode: "small", ...answers }, packs: [], modes: MODES, home: "/home/ada" });

  it("does not write Small's profile on choosing the mode, before its address is known", async () => {
    client.getInstallState.mockResolvedValue({ mode: "lite", answers: { mode: "lite" }, packs: [], modes: MODES, home: "/home/ada" });
    client.putInstallAnswers.mockResolvedValue(small({}));
    render(<InstallApp />);
    fireEvent.click(await screen.findByRole("radio", { name: /^Small/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save mode" }));
    await waitFor(() => expect(client.putInstallAnswers).toHaveBeenCalled());
    // Small's profile alone is refused (Small is HTTPS); the Domain screen writes it with its address.
    expect(client.putConfig).not.toHaveBeenCalled();
  });

  it("writes Small's profile and its https:// address together when the domain is saved", async () => {
    client.getInstallState.mockResolvedValue(small({ cloud: { provider: "aws", region: "eu-west-2" } }));
    client.putInstallAnswers.mockResolvedValue(small({ cloud: { provider: "aws", region: "eu-west-2", domain: "osprey.example.org" } }));
    client.putConfig.mockResolvedValue({ profile: "small", network: { public_origin: "https://osprey.example.org" } });
    render(<InstallApp />);
    fireEvent.click(await screen.findByRole("button", { name: "Domain" }));
    fireEvent.change(screen.getByLabelText("Domain name"), { target: { value: "osprey.example.org" } });
    fireEvent.click(screen.getByRole("button", { name: "Save domain" }));
    await waitFor(() =>
      expect(client.putConfig).toHaveBeenCalledWith({ profile: "small", network: { public_origin: "https://osprey.example.org" } }),
    );
  });
});
