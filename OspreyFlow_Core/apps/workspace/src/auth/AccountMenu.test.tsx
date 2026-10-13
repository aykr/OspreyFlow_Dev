// @vitest-environment jsdom
//
// The signed-in account, folded into one button (ADR-065). ADR-050 says the principal's identity
// and clearance are always visible in the chrome, so the clearance stays on the button; the rest
// and Sign out sit behind it.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountMenu } from "./AccountMenu";
import { displayPrincipalFromUser } from "./userManager";

afterEach(cleanup);

const PRINCIPAL = {
  sub: "2a0683a4-5a9c-40cb-94b9-e9c502084449",
  username: "osprey-demo-analyst",
  clearance: "OFFICIAL",
  orgUnit: "unit-1",
  roles: [],
  receivableHandlingCodes: [],
};

describe("AccountMenu", () => {
  it("shows who is signed in and their clearance on the button, and nothing else", () => {
    render(<AccountMenu principal={PRINCIPAL} onSignOut={() => undefined} />);
    const button = screen.getByRole("button", { name: /osprey-demo-analyst/ });
    expect(button.textContent).toContain("OFFICIAL");
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
    expect(document.body.textContent).not.toContain(PRINCIPAL.sub);
  });

  it("falls back to the subject when the token carries no user name", () => {
    render(<AccountMenu principal={{ ...PRINCIPAL, username: "" }} onSignOut={() => undefined} />);
    expect(screen.getByRole("button", { name: /2a0683a4/ }).textContent).toContain("OFFICIAL");
  });

  it("opens to the full subject, the unit and Sign out", () => {
    render(<AccountMenu principal={PRINCIPAL} onSignOut={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: /osprey-demo-analyst/ }));
    expect(screen.getByText(PRINCIPAL.sub)).toBeTruthy();
    expect(screen.getByText("unit-1")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
  });

  it("signs out when asked", () => {
    const onSignOut = vi.fn();
    render(<AccountMenu principal={PRINCIPAL} onSignOut={onSignOut} />);
    fireEvent.click(screen.getByRole("button", { name: /osprey-demo-analyst/ }));
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });
});

describe("displayPrincipalFromUser", () => {
  it("reads the user name from the token's preferred_username", () => {
    const principal = displayPrincipalFromUser({
      profile: { sub: "s1", preferred_username: "analyst-1", clearance: "OFFICIAL" },
    } as never);
    expect(principal.username).toBe("analyst-1");
  });

  it("leaves the user name empty when the token has none", () => {
    const principal = displayPrincipalFromUser({ profile: { sub: "s1" } } as never);
    expect(principal.username).toBe("");
  });
});

// ADR-115 Amendment 1: the theme is an icon in the bar, so the account menu no longer holds it.
describe("AccountMenu and the theme", () => {
  it("no longer offers the theme", () => {
    render(<AccountMenu principal={PRINCIPAL} onSignOut={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: /osprey-demo-analyst/ }));
    expect(screen.queryByRole("button", { name: /Switch to the/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
  });
});
