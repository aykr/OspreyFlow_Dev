// `06_DECISIONS.md` ADR-050 Amendment 3: a refresh keeps the person signed in. Tokens are held in
// memory only (ADR-050, `userManager.ts`'s `InMemoryStorage`), so a reload starts with none; before
// this the Glass then showed its own Sign in screen even though the identity provider still knew the
// person. Now, with no token in memory at load, the Glass first asks the identity provider's own
// session silently (`prompt=none` in a hidden frame, the same round as ADR-050 Amendment 1's renewal)
// and shows the screen only when that fails. Nothing about where tokens are kept changes.
//
// **Asked once per page load.** The answer is one promise kept for the life of the page, so React's
// development double-run of the bootstrap effect shares it rather than asking twice, and a failure
// is never followed by another silent round: it ends at the screen (or, for a hand-off, at the one
// full-page sign-in it always started). A page that is itself inside a frame never asks: the only
// frame the workspace is ever loaded in is the silent round's own (`callbackFrame.ts`), and asking
// from there would open a frame inside a frame.
import type { User } from "oidc-client-ts";

/** The words on the screen when a hand-off's sign-in could not be started (as before). */
export const AUTO_SIGN_IN_FAILED =
  "Sign-in could not be started automatically. Press Sign in to try again.";

/** The silent round at load: shorter than the renewal's 20 seconds, since the bundle the frame loads
 * was fetched a moment ago, and the person is looking at a blank page while it runs. */
export const SILENT_AT_LOAD_TIMEOUT_SECONDS = 10;

export interface SignInAtLoadSteps {
  /** The `prompt=none` round: the person when the identity provider's session is live, `null` when
   * it says there is none (`login_required`); it may throw when the provider cannot be reached. */
  silent: () => Promise<User | null>;
  /** The full-page sign-in, started without a click only for a hand-off (`launcherHandoff.ts`). */
  redirect: () => Promise<void>;
  /** This page is inside a frame. */
  framed: boolean;
  /** Arrived by a hand-off (the launcher, or a case switch's reload). */
  autoSignIn: boolean;
}

export type SignInAtLoad =
  | { kind: "signed-in"; user: User }
  | { kind: "redirected" }
  /** The Sign in screen, with a sentence of its own when there is something to say. */
  | { kind: "screen"; reason: string | null };

let thisLoad: Promise<SignInAtLoad> | null = null;

/** What a load with no token in memory comes to. The steps run at most once per page load. */
export function signInAtLoad(steps: SignInAtLoadSteps): Promise<SignInAtLoad> {
  thisLoad ??= decide(steps);
  return thisLoad;
}

async function decide(steps: SignInAtLoadSteps): Promise<SignInAtLoad> {
  if (!steps.framed) {
    try {
      const user = await steps.silent();
      if (user) return { kind: "signed-in", user };
    } catch {
      // Unreachable, timed out, or refused in a shape the library does not name: the same as no
      // session. The screen's button still works, and nothing is asked again.
    }
  }
  if (steps.autoSignIn) {
    try {
      await steps.redirect();
      return { kind: "redirected" };
    } catch {
      return { kind: "screen", reason: AUTO_SIGN_IN_FAILED };
    }
  }
  return { kind: "screen", reason: null };
}

/** Tests only: a new page load. */
export function forgetThisLoad(): void {
  thisLoad = null;
}
