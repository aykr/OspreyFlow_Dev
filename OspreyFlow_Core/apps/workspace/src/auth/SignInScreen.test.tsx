// @vitest-environment jsdom
// ADR-115 (E2): the signed-out page is the welcome page of `design/handoff/OspreyFlow Welcome.dc.html`,
// rebuilt. The password is never typed here (ADR-115 decision 4): the card starts the code flow, and
// the email form is Keycloak's own page. Organisation sign-in appears only when one is configured
// (decision 3); About and each footer link only as the deployment says (decision 8). The marking is
// the deployment's (decision 2).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SignInScreen, type WelcomeSettings } from "./SignInScreen";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-theme");
});

const PLAIN: WelcomeSettings = { organisationSignIn: null, about: true, links: {}, version: "c01833b" };

function card() {
  return within(screen.getByRole("complementary", { name: /^Sign in/ }));
}

describe("the signed-out page's marking", () => {
  it("is the deployment's", () => {
    render(<SignInScreen marking="OFFICIAL" onSignIn={() => undefined} />);
    expect(screen.getByRole("note", { name: "Protective marking" }).textContent).toBe("OFFICIAL");
  });

  it("is absent where none is known", () => {
    render(<SignInScreen onSignIn={() => undefined} />);
    expect(screen.queryByRole("note", { name: "Protective marking" })).toBeNull();
  });
});

describe("the welcome page", () => {
  it("says what the product is, with its four capabilities", () => {
    render(<SignInScreen welcome={PLAIN} onSignIn={() => undefined} />);
    expect(screen.getByRole("heading", { level: 1, name: "Crime analysis on one graph" })).toBeTruthy();
    const terms = screen.getAllByRole("term").map((t) => t.textContent);
    expect(terms.slice(0, 4)).toEqual(["Network analysis", "Geospatial", "Timeline trends", "Reporting"]);
    expect(screen.getByRole("img", { name: /Example network/ })).toBeTruthy();
  });

  it("with no organisation sign-in, offers one Sign in to the OspreyFlow page, and says it is opening", () => {
    const signIn = vi.fn();
    render(<SignInScreen welcome={PLAIN} onSignIn={signIn} />);
    expect(card().queryByRole("button", { name: /organisation/ })).toBeNull();
    expect(card().queryByRole("textbox")).toBeNull();
    fireEvent.click(card().getByRole("button", { name: "Sign in" }));
    expect(signIn).toHaveBeenCalledWith(undefined);
    const busy = card().getByRole("button", { name: "Opening the sign-in page…" });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
  });

  it("with organisation sign-in, offers it first and an OspreyFlow account second", () => {
    const signIn = vi.fn();
    render(<SignInScreen welcome={{ ...PLAIN, organisationSignIn: "acme-entra" }} onSignIn={signIn} />);
    expect(card().getByText("Your password is entered only on your organisation's sign-in page.")).toBeTruthy();
    expect(card().getByText("or use an OspreyFlow account")).toBeTruthy();
    fireEvent.click(card().getByRole("button", { name: "Sign in with an OspreyFlow account" }));
    expect(signIn).toHaveBeenLastCalledWith(undefined);
    cleanup();
    render(<SignInScreen welcome={{ ...PLAIN, organisationSignIn: "acme-entra" }} onSignIn={signIn} />);
    fireEvent.click(card().getByRole("button", { name: "Continue with organisation sign-in" }));
    expect(signIn).toHaveBeenLastCalledWith("acme-entra");
    expect(card().getByRole("button", { name: "Opening your organisation's sign-in page…" })).toBeTruthy();
  });

  it("says which place a hand-off is signing in to", () => {
    render(<SignInScreen welcome={PLAIN} intent="ingest" onSignIn={() => undefined} />);
    expect(card().getByRole("heading", { name: "Sign in to the Ingest Studio" })).toBeTruthy();
  });

  it("says why a sign-in failed, in the card", () => {
    render(<SignInScreen welcome={PLAIN} reason="The identity provider could not be reached." onSignIn={() => undefined} />);
    expect(card().getByRole("alert").textContent).toContain("The identity provider could not be reached.");
  });

  it("shows About unless the deployment switches it off", () => {
    render(<SignInScreen welcome={PLAIN} onSignIn={() => undefined} />);
    expect(screen.getByRole("heading", { level: 2, name: "Two kinds of work, one graph" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "About" }).getAttribute("href")).toBe("#about");
    cleanup();
    render(<SignInScreen welcome={{ ...PLAIN, about: false }} onSignIn={() => undefined} />);
    expect(screen.queryByRole("heading", { name: "Two kinds of work, one graph" })).toBeNull();
    expect(screen.queryByRole("link", { name: "About" })).toBeNull();
  });

  it("links only the documents the deployment gives, and names its version in mono", () => {
    render(
      <SignInScreen
        welcome={{ ...PLAIN, links: { account_help: "https://help.test/", privacy: "https://privacy.test/" } }}
        onSignIn={() => undefined}
      />,
    );
    const footer = within(screen.getByRole("navigation", { name: "Footer" }));
    expect(footer.getAllByRole("link").map((a) => a.textContent)).toEqual(["Account help", "Privacy notice"]);
    // A link with no address is not a link to assistive technology, so the words are checked too.
    expect(screen.getByRole("navigation", { name: "Footer" }).textContent).toBe("Account helpPrivacy notice");
    expect(card().getByRole("link", { name: "Get account help" }).getAttribute("href")).toBe("https://help.test/");
    expect(screen.getByText("c01833b").className).toContain("value");
  });

  it("has no account-help sentence where no help address is given", () => {
    render(<SignInScreen welcome={PLAIN} onSignIn={() => undefined} />);
    expect(card().getByText(/Your OspreyFlow administrator invites people and assigns roles\./)).toBeTruthy();
    expect(card().queryByText(/Get account help/)).toBeNull();
  });

  it("switches the theme from its header, the button saying what it will do", () => {
    render(<SignInScreen welcome={PLAIN} onSignIn={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(screen.getByRole("button", { name: "Dark theme" })).toBeTruthy();
  });
});
