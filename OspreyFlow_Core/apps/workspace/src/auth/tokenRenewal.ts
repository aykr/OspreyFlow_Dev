// `06_DECISIONS.md` ADR-050 Amendment 1 (build order step 18b, rehearsal defect D1): the access token
// is renewed silently in the background before it expires, so a window lasts as long as the identity
// provider's session; tokens stay short.
//
// **Why automatic renewal was off, and why that race cannot happen here.** `userManager.ts` set
// `automaticSilentRenew: false` so the library's own timer could not fire in the middle of the Glass's
// explicit re-authentication after a 401. Here there is one renewal at a time: the timer and every
// refused call ask the same `renewNow`, and while a renewal is in flight each later ask is given that
// same renewal's outcome rather than starting another. The library's timer stays off.
//
// **Only after the person has done something** (ADR-050 Amendment 2, build order step 28 (b)). Each
// renewal is a sign-in round at the identity provider, which counts as activity there, so renewing
// an open, unattended window kept its session alive to the maximum (10 hours) and never let the idle
// limit end it. A renewal is now made only if the person has pressed a key, pressed a pointer or
// turned a wheel (`ACTIVITY_EVENTS`) since the last renewal or sign-in. Otherwise the token lapses:
// nothing is asked and nothing renewed until they come back, when their first action renews it at
// once — and if the identity provider's idle limit has passed by then, that renewal answers
// `login_required` and the session prompt asks them in place (Amendment 1 point 4).

/** What the renewal was given back: the identity provider's answer, as `userManager.renewSilently`
 * gives it (`null` when its session has ended). Only these three fields are read. */
export interface RenewedUser {
  access_token: string;
  expires_at?: number;
  profile: { sub?: string };
}

export type RenewalOutcome =
  | { kind: "renewed"; token: string }
  /** The identity provider's own session has ended (`login_required`): a person must sign in. */
  | { kind: "ended" }
  /** The identity provider could not be reached, or did not answer in time (ADR-044's distinction:
   * an outage, not a decision about the person). */
  | { kind: "unreachable" }
  /** Not asked: nobody has done anything since the last renewal or sign-in (Amendment 2). */
  | { kind: "idle" };

export interface TokenRenewalOptions {
  renew: () => Promise<RenewedUser | null>;
  onRenewed: (user: RenewedUser) => void;
  onEnded: (why: "ended" | "unreachable") => void;
  /** How long before expiry to renew, at most; a short token is renewed half-way through its life. */
  leadSeconds?: number;
}

export interface TokenRenewal {
  /** Renew now, whatever the activity (the person asked: *Try again*), or join the renewal already
   * in flight. */
  renewNow: () => Promise<RenewalOutcome>;
  /** Renew if the person has done something since the last renewal or sign-in, or join the renewal
   * in flight; otherwise `idle`, and their next action renews. For a call the Conduit refused. */
  renewIfActive: () => Promise<RenewalOutcome>;
  /** The person did something (`watchActivity`). Renews at once if the token was left to lapse. */
  noteActivity: () => void;
  /** A sign-in's token: renew ahead of this expiry (seconds since the epoch, as a token's
   * `expires_at`), if the person does something before then. Activity is counted from here. */
  schedule: (expiresAt: number | undefined) => void;
  dispose: () => void;
}

export const DEFAULT_LEAD_SECONDS = 60;

/** What counts as the person doing something: deliberate actions only, each cheap to notice. A
 * pointer merely moving is not one (a resting mouse can jitter); a pointer press covers touch. */
export const ACTIVITY_EVENTS = ["keydown", "pointerdown", "wheel"] as const;

/** Calls `onActivity` on each of `ACTIVITY_EVENTS` anywhere under `target`, listening passively in
 * the capture phase (so a handler that stops an event does not hide it, and no scroll waits on us).
 * The handler only sets a flag. Returns the function that stops listening. */
export function watchActivity(target: EventTarget, onActivity: () => void): () => void {
  const options: AddEventListenerOptions = { capture: true, passive: true };
  const handler = () => onActivity();
  for (const type of ACTIVITY_EVENTS) target.addEventListener(type, handler, options);
  return () => {
    for (const type of ACTIVITY_EVENTS) target.removeEventListener(type, handler, options);
  };
}

export function createTokenRenewal(options: TokenRenewalOptions): TokenRenewal {
  const leadMs = (options.leadSeconds ?? DEFAULT_LEAD_SECONDS) * 1000;
  let inFlight: Promise<RenewalOutcome> | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;
  /** The person has done something since the last renewal or sign-in. */
  let active = false;
  /** A renewal was due (or a call refused) while nobody was doing anything: the next action renews. */
  let lapsed = false;

  function clear(): void {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }

  function arm(expiresAt: number | undefined): void {
    clear();
    if (disposed || expiresAt === undefined) return;
    const remaining = expiresAt * 1000 - Date.now();
    const delay = Math.max(0, remaining - Math.min(leadMs, remaining / 2));
    timer = setTimeout(() => {
      timer = null;
      void renewIfActive();
    }, delay);
  }

  function schedule(expiresAt: number | undefined): void {
    active = false;
    lapsed = false;
    arm(expiresAt);
  }

  function renewIfActive(): Promise<RenewalOutcome> {
    if (inFlight) return inFlight;
    if (!active) {
      lapsed = !disposed;
      return Promise.resolve({ kind: "idle" });
    }
    return renewNow();
  }

  function noteActivity(): void {
    active = true;
    if (lapsed && !inFlight && !disposed) void renewNow();
  }

  function renewNow(): Promise<RenewalOutcome> {
    if (inFlight) return inFlight;
    clear();
    active = false;
    lapsed = false;
    inFlight = (async (): Promise<RenewalOutcome> => {
      try {
        let user: RenewedUser | null;
        try {
          user = await options.renew();
        } catch {
          options.onEnded("unreachable");
          return { kind: "unreachable" };
        }
        if (!user) {
          options.onEnded("ended");
          return { kind: "ended" };
        }
        arm(user.expires_at);
        options.onRenewed(user);
        return { kind: "renewed", token: user.access_token };
      } finally {
        inFlight = null;
      }
    })();
    return inFlight;
  }

  return {
    renewNow,
    renewIfActive,
    noteActivity,
    schedule,
    dispose: () => {
      disposed = true;
      lapsed = false;
      clear();
    },
  };
}
