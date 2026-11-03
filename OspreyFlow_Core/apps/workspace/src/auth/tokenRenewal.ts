// `06_DECISIONS.md` ADR-050 Amendment 1 (build order step 18b, rehearsal defect D1): the access token
// is renewed silently in the background before it expires, so a window lasts as long as the identity
// provider's session; tokens stay short.
//
// **Why automatic renewal was off, and why that race cannot happen here.** `userManager.ts` set
// `automaticSilentRenew: false` so the library's own timer could not fire in the middle of the Glass's
// explicit re-authentication after a 401. Here there is one renewal at a time: the timer and every
// refused call ask the same `renewNow`, and while a renewal is in flight each later ask is given that
// same renewal's outcome rather than starting another. The library's timer stays off.

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
  | { kind: "unreachable" };

export interface TokenRenewalOptions {
  renew: () => Promise<RenewedUser | null>;
  onRenewed: (user: RenewedUser) => void;
  onEnded: (why: "ended" | "unreachable") => void;
  /** How long before expiry to renew, at most; a short token is renewed half-way through its life. */
  leadSeconds?: number;
}

export interface TokenRenewal {
  /** Renew now, or join the renewal already in flight. */
  renewNow: () => Promise<RenewalOutcome>;
  /** Renew ahead of this expiry (seconds since the epoch, as a token's `expires_at`). */
  schedule: (expiresAt: number | undefined) => void;
  dispose: () => void;
}

export const DEFAULT_LEAD_SECONDS = 60;

export function createTokenRenewal(options: TokenRenewalOptions): TokenRenewal {
  const leadMs = (options.leadSeconds ?? DEFAULT_LEAD_SECONDS) * 1000;
  let inFlight: Promise<RenewalOutcome> | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;

  function clear(): void {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }

  function schedule(expiresAt: number | undefined): void {
    clear();
    if (disposed || expiresAt === undefined) return;
    const remaining = expiresAt * 1000 - Date.now();
    const delay = Math.max(0, remaining - Math.min(leadMs, remaining / 2));
    timer = setTimeout(() => {
      timer = null;
      void renewNow();
    }, delay);
  }

  function renewNow(): Promise<RenewalOutcome> {
    if (inFlight) return inFlight;
    clear();
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
        schedule(user.expires_at);
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
    schedule,
    dispose: () => {
      disposed = true;
      clear();
    },
  };
}
