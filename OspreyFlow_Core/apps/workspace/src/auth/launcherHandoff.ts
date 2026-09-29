// What the launcher (`make launch`) tells the Glass when it opens it: `?from=launcher`, and
// `&view=ingest` for the Ingest Studio tile. It exists so a person who has just signed in at the
// launcher is not asked to sign in again by the Glass, and so the Studio tile opens on the Studio
// rather than on the same page as the Glass tile.
//
// **It grants nothing.** The Glass still runs its own sign-in (authorization code with PKCE); the
// identity provider recognises the person from the launcher's sign-in, so no password is asked.
// The Conduit still checks every request against the token's roles (`06_DECISIONS.md` ADR-050);
// nothing here can widen what a token allows. All this decides is whether that sign-in starts
// without a click, and which tab to open first.
//
// The query is gone after the identity provider's round trip (it returns to the Glass's root), so
// the tab choice is kept in `sessionStorage` for a short while. It is a preference about a screen,
// not state that matters: unreadable, expired or foreign values are ignored, and storage that
// refuses to work degrades to "start the sign-in, open the default tab".

export type HandoffView = "ingest";

export interface Handoff {
  /** Start the sign-in without waiting for a click. */
  autoSignIn: boolean;
  view: HandoffView | null;
}

export const HANDOFF_STORAGE_KEY = "ospreyflow.launcherHandoff";
/** A choice left behind by a sign-in nobody finished must not surprise a later, unrelated visit. */
export const HANDOFF_MAX_AGE_MS = 10 * 60 * 1000;

interface Stash {
  view: HandoffView | null;
  at: number;
}

function viewFrom(value: unknown): HandoffView | null {
  return value === "ingest" ? "ingest" : null;
}

function stash(storage: Storage, value: Stash): void {
  try {
    storage.setItem(HANDOFF_STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* a preference about a screen: not worth failing a sign-in over */
  }
}

function stashed(storage: Storage, now: number): HandoffView | null {
  try {
    const raw = storage.getItem(HANDOFF_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<Stash> | null;
    if (!value || typeof value.at !== "number") return null;
    if (now - value.at > HANDOFF_MAX_AGE_MS) return null;
    return viewFrom(value.view);
  } catch {
    return null;
  }
}

/** Reads the hand-off from the address the Glass was opened with. Arriving from the launcher also
 * records the chosen tab, replacing any earlier choice, so that it survives the trip to the
 * identity provider and back. */
export function readHandoff(
  search: string,
  storage: Storage,
  now: number = Date.now(),
): Handoff {
  const params = new URLSearchParams(search);
  if (params.get("from") === "launcher") {
    const view = viewFrom(params.get("view"));
    stash(storage, { view, at: now });
    return { autoSignIn: true, view };
  }
  return { autoSignIn: false, view: stashed(storage, now) };
}

/** Called once the sign-in has completed, so the choice is not applied to a later visit. */
export function clearHandoff(storage: Storage): void {
  try {
    storage.removeItem(HANDOFF_STORAGE_KEY);
  } catch {
    /* nothing to clear */
  }
}
