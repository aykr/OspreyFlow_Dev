// ADR-050 Amendment 3: a refresh keeps the person signed in. The decision at load, given what
// `renewSilently` (`userManager.ts`) returns: the person when the identity provider's session is live,
// `null` for its `login_required`, or an error. This is a stand-in for that function's answer, not a
// fake provider: the fake that refuses `prompt=none` as Keycloak does, driven through the real
// `oidc-client-ts`, is `keyboard/refresh-sign-in.spec.ts`'s, and Keycloak itself answers in
// `tests/harness/test_refresh_silent_sign_in_keycloak.py`.
import { afterEach, describe, expect, it, vi } from "vitest";

import { AUTO_SIGN_IN_FAILED, forgetThisLoad, signInAtLoad, type SignInAtLoadSteps } from "./signInAtLoad";

/** Keycloak's authorisation endpoint, as far as a `prompt=none` round is concerned. */
function fakeIdentityProvider(session: { sub: string } | null) {
  const asked: string[] = [];
  return {
    asked,
    /** The round as `renewSilently` sees it: the person, or `null` for Keycloak's `login_required`. */
    silent: vi.fn(async () => {
      asked.push("prompt=none");
      if (!session) {
        // What Keycloak answers: `error=login_required` on the redirect, which the library raises
        // as an `ErrorResponse` and `renewSilently` returns as `null`.
        return null;
      }
      return { access_token: `token-for-${session.sub}`, profile: { sub: session.sub } } as never;
    }),
  };
}

function steps(over: Partial<SignInAtLoadSteps> = {}): SignInAtLoadSteps {
  return { silent: vi.fn(async () => null), redirect: vi.fn(async () => undefined), framed: false, autoSignIn: false, ...over };
}

afterEach(() => forgetThisLoad());

describe("signInAtLoad", () => {
  it("a refresh with a live identity-provider session lands signed in, without the screen", async () => {
    const idp = fakeIdentityProvider({ sub: "analyst-1" });
    const redirect = vi.fn(async () => undefined);
    const outcome = await signInAtLoad(steps({ silent: idp.silent, redirect }));
    expect(outcome.kind).toBe("signed-in");
    expect(outcome.kind === "signed-in" && outcome.user.access_token).toBe("token-for-analyst-1");
    expect(redirect).not.toHaveBeenCalled();
  });

  it("a refresh with no session: the fake refuses prompt=none as Keycloak does, and the screen shows with its own sentence", async () => {
    const idp = fakeIdentityProvider(null);
    const outcome = await signInAtLoad(steps({ silent: idp.silent }));
    expect(idp.asked).toEqual(["prompt=none"]);
    // `null`: the screen's own lead sentence, nothing about an error the person did not meet.
    expect(outcome).toEqual({ kind: "screen", reason: null });
  });

  it("an identity provider that cannot be reached (the round throws or times out) also ends at the screen", async () => {
    const outcome = await signInAtLoad(steps({ silent: vi.fn(async () => Promise.reject(new Error("IFrame timed out without a response"))) }));
    expect(outcome).toEqual({ kind: "screen", reason: null });
  });

  it("a silent failure never loops: the provider is asked once per load, however often the bootstrap runs", async () => {
    const idp = fakeIdentityProvider(null);
    const redirect = vi.fn(async () => undefined);
    // React's development double-run, and any later re-run of the effect, share the one answer.
    const all = await Promise.all([1, 2, 3].map(() => signInAtLoad(steps({ silent: idp.silent, redirect }))));
    await signInAtLoad(steps({ silent: idp.silent, redirect }));
    expect(idp.silent).toHaveBeenCalledTimes(1);
    expect(redirect).not.toHaveBeenCalled();
    expect(new Set(all.map((o) => o.kind))).toEqual(new Set(["screen"]));
  });

  it("a page inside a frame never asks (the silent round's own frame would open another)", async () => {
    const idp = fakeIdentityProvider({ sub: "analyst-1" });
    const outcome = await signInAtLoad(steps({ silent: idp.silent, framed: true }));
    expect(idp.silent).not.toHaveBeenCalled();
    expect(outcome).toEqual({ kind: "screen", reason: null });
  });

  it("a hand-off with a live session signs in silently, with no full-page round trip", async () => {
    const idp = fakeIdentityProvider({ sub: "analyst-1" });
    const redirect = vi.fn(async () => undefined);
    const outcome = await signInAtLoad(steps({ silent: idp.silent, redirect, autoSignIn: true }));
    expect(outcome.kind).toBe("signed-in");
    expect(redirect).not.toHaveBeenCalled();
  });

  it("a hand-off with no session starts the full-page sign-in once, as before", async () => {
    const idp = fakeIdentityProvider(null);
    const redirect = vi.fn(async () => undefined);
    expect(await signInAtLoad(steps({ silent: idp.silent, redirect, autoSignIn: true }))).toEqual({ kind: "redirected" });
    await signInAtLoad(steps({ silent: idp.silent, redirect, autoSignIn: true }));
    expect(redirect).toHaveBeenCalledTimes(1);
  });

  it("a hand-off whose sign-in cannot be started shows the screen with the sentence that says so", async () => {
    const outcome = await signInAtLoad(steps({ autoSignIn: true, redirect: vi.fn(async () => Promise.reject(new Error("no"))) }));
    expect(outcome).toEqual({ kind: "screen", reason: AUTO_SIGN_IN_FAILED });
  });
});
