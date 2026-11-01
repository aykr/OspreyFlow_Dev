// @vitest-environment jsdom
// ADR-115 (E2): the signed-out page is the welcome page of `design/handoff/OspreyFlow Welcome.dc.html`,
// rebuilt. The password is never typed here (ADR-115 decision 4): the card starts the code flow, and
// the email form is Keycloak's own page. Organisation sign-in appears only when one is configured
// (decision 3); About and each footer link only as the deployment says (decision 8). The marking is
// the deployment's (decision 2).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { applyBrand } from "../brand/brand";
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
  // ADR-115 Amendment 4 (the owner, 1 November 2026): intelligence mapping first, then what it is
  // for, with event monitoring and alerting a key capability.
  it("says what the product is, with its five capabilities", () => {
    render(<SignInScreen welcome={PLAIN} onSignIn={() => undefined} />);
    expect(screen.getByRole("heading", { level: 1, name: "Intelligence mapping" })).toBeTruthy();
    expect(screen.getByText(/^For crime analysis, anti-money-laundering, fraud detection, and event monitoring and alerting\./)).toBeTruthy();
    const terms = screen.getAllByRole("term").map((t) => t.textContent);
    expect(terms.slice(0, 5)).toEqual(["Network analysis", "Geospatial", "Timeline trends", "Monitoring and alerts", "Reporting"]);
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
    expect(screen.getByRole("heading", { level: 2, name: "One intelligence map" })).toBeTruthy();
    const parts = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(parts).toEqual(["Crime analysis", "Anti-money-laundering", "Fraud detection", "Event monitoring and alerting"].concat(parts.slice(4)));
    expect(screen.getByRole("link", { name: "About" }).getAttribute("href")).toBe("#about");
    cleanup();
    render(<SignInScreen welcome={{ ...PLAIN, about: false }} onSignIn={() => undefined} />);
    expect(screen.queryByRole("heading", { name: "One intelligence map" })).toBeNull();
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

// ADR-132 Amendment 4 (the owner, 1 November 2026: "this box is very confusing to read"): under
// GOV.UK the card is a heading, one plain sentence, the button and who to ask, and names no product
// (ruling 7). The OspreyFlow brand's card is ADR-115 E2's and is unchanged.
describe("under GOV.UK, the sign-in card", () => {
  afterEach(() => applyBrand("ospreyflow"));

  it("is the heading, one sentence, the button and who to ask, naming no product", () => {
    applyBrand("govuk");
    render(<SignInScreen welcome={PLAIN} onSignIn={() => undefined} />);
    const box = screen.getByRole("complementary", { name: "Sign in" });
    expect(box.textContent).toBe(
      "Sign in" +
        "You'll see only the cases your role and clearance allow. Your activity is recorded." +
        "Sign in" +
        "No account? Ask your administrator.",
    );
  });

  it("with organisation sign-in, offers it first and a username and password second, naming no product", () => {
    applyBrand("govuk");
    const signIn = vi.fn();
    render(<SignInScreen welcome={{ ...PLAIN, organisationSignIn: "acme-entra" }} onSignIn={signIn} />);
    const box = screen.getByRole("complementary", { name: "Sign in" });
    expect(box.textContent).not.toMatch(/OspreyFlow|password is entered/);
    expect(card().getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Continue with organisation sign-in",
      "Sign in with a username and password",
    ]);
    fireEvent.click(card().getByRole("button", { name: "Sign in with a username and password" }));
    expect(signIn).toHaveBeenCalledWith(undefined);
  });

  it("keeps the account-help link where the deployment gives one", () => {
    applyBrand("govuk");
    render(<SignInScreen welcome={{ ...PLAIN, links: { account_help: "https://help.test/" } }} onSignIn={() => undefined} />);
    expect(card().getByText(/^No account\? Ask your administrator\./)).toBeTruthy();
    expect(card().getByRole("link", { name: "Get account help" }).getAttribute("href")).toBe("https://help.test/");
  });

  // ADR-132 Amendment 4: the product's identity is in the About section, nowhere else on the page.
  it("names OspreyFlow, with its mark and version, in the About section only", () => {
    applyBrand("govuk");
    render(<SignInScreen welcome={{ ...PLAIN, links: { privacy: "https://privacy.test/" } }} onSignIn={() => undefined} />);
    const about = document.getElementById("about")!;
    const identity = within(about).getByRole("region", { name: "About OspreyFlow" });
    expect(identity.textContent).toContain("OspreyFlow is the open-source intelligence analysis and network discovery platform this service is built on.");
    expect(within(identity).getByText("c01833b")).toBeTruthy();
    expect(identity.querySelector("svg")).not.toBeNull();
    about.remove();
    expect(document.body.textContent).not.toMatch(/OspreyFlow/);
    // The page's own footer keeps its links.
    expect(screen.getByRole("link", { name: "Privacy notice" })).toBeTruthy();
  });

  it("under the OspreyFlow brand has no separate About OspreyFlow block", () => {
    render(<SignInScreen welcome={PLAIN} onSignIn={() => undefined} />);
    expect(screen.queryByRole("region", { name: "About OspreyFlow" })).toBeNull();
  });
});
