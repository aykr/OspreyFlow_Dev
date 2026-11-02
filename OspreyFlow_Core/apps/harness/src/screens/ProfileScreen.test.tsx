// @vitest-environment jsdom
//
// The Profile screen (Set-up console, and the guided page's Lite list). S11, the owner's ruling of
// 2 November 2026: Small and Enterprise are HTTPS, and `osprey.yaml` refuses either profile at a
// plain-HTTP address. So choosing one asks for its https:// address and saves the two in one write;
// the profile alone, at Lite's address, would be refused. Lite saves its profile alone, as before.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({ postConsequences: vi.fn() }));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  ...client,
}));

import { ProfileScreen } from "./ProfileScreen";

beforeEach(() => {
  client.postConsequences.mockReset().mockResolvedValue({ profile: "small", machines: "1", memory_gb_floor: 16, orchestrator: "compose" });
});
afterEach(cleanup);

describe("ProfileScreen", () => {
  it("asks Small for its https:// address and saves the profile and the address together", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ProfileScreen config={{ profile: "local-lite", network: { expose_conduit: false } }} onSave={onSave} />);
    expect(screen.queryByRole("textbox", { name: /Address/ })).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: /^small/ }));
    const address = screen.getByRole("textbox", { name: /^Address/ });
    expect(address).toHaveProperty("required", true);
    expect(screen.getByText(/reached by other people over a network, so its address is HTTPS/)).toBeTruthy();
    fireEvent.change(address, { target: { value: "https://osprey.example.org" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        profile: "small",
        network: { expose_conduit: false, public_origin: "https://osprey.example.org" },
      }),
    );
  });

  it("offers the deployment's own HTTPS address when it has one", () => {
    render(<ProfileScreen config={{ profile: "small", network: { public_origin: "https://intel.example.org" } }} onSave={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: /^Address/ })).toHaveProperty("value", "https://intel.example.org");
  });

  it("saves Lite's profile alone", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ProfileScreen config={{ profile: "small" }} onSave={onSave} />);
    fireEvent.click(screen.getByRole("radio", { name: /^local-lite/ }));
    expect(screen.queryByRole("textbox", { name: /^Address/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ profile: "local-lite" }));
  });
});
