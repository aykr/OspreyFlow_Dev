// ADR-050 Amendment 1: the silent renewal is ADR-050's own `prompt=none` round, run in a hidden
// iframe on the workspace's own origin (no refresh token is held). The identity provider sends that
// iframe back to the workspace's address with the answer, so the page loaded there must hand the
// answer to the window that asked and draw nothing: it is not a second workspace. The sign-in
// window opened when a session has ended does the same for its opener.
import { describe, expect, it, vi } from "vitest";

import { SIGN_IN_WINDOW_NAME, answerTheWindowThatAsked } from "./callbackFrame";

const ORIGIN = "http://govuk.ospreyflow.localhost:8081";

function page(opts: { search: string; framed?: boolean; opener?: boolean; name?: string }) {
  const parent = { postMessage: vi.fn() };
  const opener = opts.opener ? { postMessage: vi.fn() } : null;
  const win = {
    location: { href: `${ORIGIN}/${opts.search}`, search: opts.search, origin: ORIGIN },
    name: opts.name ?? "",
    opener,
    parent: null as unknown,
  };
  win.parent = opts.framed ? parent : win;
  return { win: win as unknown as Window, parent, opener };
}

describe("answerTheWindowThatAsked", () => {
  it("in the silent-renewal iframe, hands the answer to the parent on the same origin and says so", () => {
    const { win, parent } = page({ search: "?code=c&state=s1", framed: true });
    expect(answerTheWindowThatAsked(win)).toBe(true);
    expect(parent.postMessage).toHaveBeenCalledWith(
      { source: "oidc-client", url: `${ORIGIN}/?code=c&state=s1`, keepOpen: false },
      ORIGIN,
    );
  });

  it("hands an ended session's refusal back too (login_required), so the parent can say so", () => {
    const { win, parent } = page({ search: "?error=login_required&state=s1", framed: true });
    expect(answerTheWindowThatAsked(win)).toBe(true);
    expect(parent.postMessage).toHaveBeenCalledTimes(1);
  });

  it("in the sign-in window, hands the answer to its opener", () => {
    const { win, opener } = page({ search: "?code=c&state=s2", opener: true, name: SIGN_IN_WINDOW_NAME });
    expect(answerTheWindowThatAsked(win)).toBe(true);
    expect(opener!.postMessage).toHaveBeenCalledWith(
      { source: "oidc-client", url: `${ORIGIN}/?code=c&state=s2`, keepOpen: false },
      ORIGIN,
    );
  });

  it("an ordinary sign-in's return, in the top window, is left to the workspace", () => {
    const { win } = page({ search: "?code=c&state=s3" });
    expect(answerTheWindowThatAsked(win)).toBe(false);
  });

  it("a workspace opened from another window (the launcher) completes its own sign-in", () => {
    const { win, opener } = page({ search: "?code=c&state=s4", opener: true });
    expect(answerTheWindowThatAsked(win)).toBe(false);
    expect(opener!.postMessage).not.toHaveBeenCalled();
  });

  it("a framed page with no answer in its address is not treated as one", () => {
    const { win, parent } = page({ search: "?case=c1", framed: true });
    expect(answerTheWindowThatAsked(win)).toBe(false);
    expect(parent.postMessage).not.toHaveBeenCalled();
  });
});
