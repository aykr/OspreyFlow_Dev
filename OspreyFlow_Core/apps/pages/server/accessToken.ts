/**
 * The bearer the page service sends the Conduit for a person (ADR-152 decision 5; slices PL10 and PL9b), and the renewal of it.
 *
 * `accessTokenFor(session)` is the one place that says which token a session's calls carry, and every call site awaits it. When
 * the access token is within `RENEWAL_MARGIN_SECONDS` of its end, the refresh token held on the server is exchanged at the
 * provider's token address, the session record is updated (the access token and its end, the new refresh token when the
 * provider rotates it, the provider's own session end) and the new token is returned. The forwarder and every other call
 * site are as they were: they pass the record they hold, and the record is what changes.
 *
 * HOW A RECORD REACHES THE RENEWAL. The record carries no reference to the provider or to the request, so a request binds its
 * own record once (`bindRenewal`, from the app's middleware) and `accessTokenFor` finds the binding by the record's identity. A
 * record that is not bound (a sign-in's own, the sign-out's) is returned as it is: no exchange is made for it.
 *
 * SINGLE FLIGHT. A person's page makes several calls at once, each with its own copy of the session record. The copies are
 * one session, and a rotating provider revokes the session when a refresh token is presented twice. So the renewal keeps, in
 * this process, one entry for each session (named by a hash of its anti-forgery token, which is the session's alone): at most one
 * exchange is in flight for it, every other call waits for that one, and every copy is brought up to the latest renewal
 * (`renewals`, a count the record carries) before it is looked at, so a copy read before the exchange never presents the spent
 * token again. This is per process: a second page-service process would not see the first's entries (the deployment runs one;
 * the cost is stated in `README.md`).
 *
 * WHAT THE PROVIDER'S ANSWERS MEAN (ADR-044). A refusal (an expired or revoked refresh token, `invalid_grant`, a wrong client
 * secret, an answer that is not a token response) ends the session: it is destroyed, its cookie cleared, and the caller is
 * given `SessionEnded`, which the app turns into the sign-in redirect on a page request and a plain 401 on a script's. A provider
 * that cannot be reached is not a decision about the person: while the access token held is still good it is used as it is (the
 * next try is after `UNREACHABLE_COOL_OFF_SECONDS`), and only when it has ended does the session end, in words that say the
 * provider could not be reached and never that access was revoked. A request that provably never arrived (refused
 * connection, a gateway's 503) is tried again after `DEFAULT_BACKOFF_MS`; one that may have been received (a time-out, a reset,
 * a 500) is **not**: the token may be spent, so it is never presented again.
 *
 * NO TOKEN IS EVER LOGGED OR PUT IN AN ERROR. What is logged is `pages: session ended: <class>`, a word of ours.
 */
import { createHash } from "node:crypto";

import { IdentityProviderRefused, IdentityProviderUnavailable } from "./identity.js";
import type { RenewedTokens } from "./identity.js";
import { IDLE_SECONDS } from "./sessionPolicy.js";
import type { SessionRecord } from "./sessionPolicy.js";

/** An access token with this many seconds or fewer left is renewed. */
export const RENEWAL_MARGIN_SECONDS = 60;
/** How long to wait before each further try of an exchange that provably never arrived: three tries, about a second. */
export const DEFAULT_BACKOFF_MS: readonly number[] = [250, 750];
/** After an exchange fails for want of a provider, how long before another is tried, so that no request waits out the retries. */
export const UNREACHABLE_COOL_OFF_SECONDS = 10;
/** A session this young that is refused is told so, not sent round again: a redirect would sign in and be refused without end. */
export const RECENT_SIGN_IN_SECONDS = 30;

/** Why a session ended, as a word of ours from a closed list: what the log says, and nothing of the provider's words. */
export type EndReason = "refused" | "unavailable" | "no_refresh_token" | "unexpected";

/** The session is over: the provider will not renew it (or cannot, and the token has ended). It is already destroyed. */
export class SessionEnded extends Error {
  readonly reason: EndReason;
  /** True when the person signed in moments ago: a redirect to sign in again would only repeat this. */
  readonly recentSignIn: boolean;

  constructor(reason: EndReason, recentSignIn: boolean) {
    super(`the session ended: ${reason}`);
    this.name = "SessionEnded";
    this.reason = reason;
    this.recentSignIn = recentSignIn;
  }
}

export interface RenewalOptions {
  /** Milliseconds to wait before each further try of an exchange that never arrived. A test shortens it. */
  backoffMs?: readonly number[];
  /** Waits. A test records the waits and returns at once. */
  sleep?: (ms: number) => Promise<void>;
}

/** What a request gives the renewal, once, for its own session record. */
export interface RenewalHooks {
  /** Writes the record to the store now, so that a renewal is not lost if the response never ends. */
  persist(): Promise<void>;
  /** Ends the session: destroys it, clears its cookie, says so in the log. Safe to call twice. */
  end(reason: EndReason): Promise<void>;
}

export interface Renewal {
  /** Makes `accessTokenFor(record)` renew this request's record. */
  bind(record: SessionRecord, hooks: RenewalHooks): void;
}

interface Binding {
  renewal: RenewalImpl;
  hooks: RenewalHooks;
}

const bound = new WeakMap<SessionRecord, Binding>();

/** The token the session's calls carry; renewed first when it is within the margin of its end. */
export async function accessTokenFor(session: SessionRecord): Promise<string> {
  const binding = bound.get(session);
  if (binding === undefined) return session.accessToken;
  return binding.renewal.tokenFor(session, binding.hooks);
}

/** The `exp` of a JWT in milliseconds, or undefined for anything that is not one. Unverified: only dates a token the provider gave us. */
function jwtExpiry(token: string): number | undefined {
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1] ?? "", "base64url").toString("utf8")) as { exp?: unknown };
    return typeof payload.exp === "number" && Number.isFinite(payload.exp) ? payload.exp * 1000 : undefined;
  } catch {
    return undefined;
  }
}

/** When the record's access token ends, as far as it can be told. */
function expiryOf(record: SessionRecord): number | undefined {
  return record.accessTokenExpiresAt ?? jwtExpiry(record.accessToken);
}

interface Latest {
  renewals: number;
  accessToken: string;
  accessTokenExpiresAt: number | undefined;
  refreshToken: string;
  idToken: string | undefined;
  idpSessionExpiresAt: number | undefined;
}

type Outcome = { kind: "renewed" } | { kind: "refused" } | { kind: "unavailable"; spent: boolean } | { kind: "unexpected" };

interface Entry {
  /** The newest tokens this process has renewed the session to: what every older copy of the record is brought up to. */
  latest?: Latest;
  inflight?: Promise<Outcome>;
  /** Set once the provider has refused: every later copy of the record is ended without asking again. */
  ended?: EndReason;
  /** No exchange is tried before this (milliseconds), because the provider could not be reached. */
  coolOffUntil?: number;
  /** An exchange may have been received and its token spent: it is never presented again. */
  spent?: boolean;
  touched: number;
}

export interface RenewalDeps {
  /** The exchange itself: `CodeFlowProvider.refresh`. */
  refresh(refreshToken: string): Promise<RenewedTokens>;
  now: () => number;
  /** Where the service says what went wrong: a fixed phrase, never a token. */
  log: (message: string) => void;
  options?: RenewalOptions;
}

class RenewalImpl implements Renewal {
  private readonly entries = new Map<string, Entry>();
  private readonly backoff: readonly number[];
  private readonly sleep: (ms: number) => Promise<void>;
  private swept = 0;

  constructor(private readonly deps: RenewalDeps) {
    this.backoff = deps.options?.backoffMs ?? DEFAULT_BACKOFF_MS;
    this.sleep = deps.options?.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  }

  bind(record: SessionRecord, hooks: RenewalHooks): void {
    bound.set(record, { renewal: this, hooks });
  }

  private entryFor(record: SessionRecord): Entry {
    const now = this.deps.now();
    this.sweep(now);
    const key = createHash("sha256").update(record.csrfToken).digest("hex");
    let entry = this.entries.get(key);
    if (entry === undefined) {
      entry = { touched: now };
      this.entries.set(key, entry);
    }
    entry.touched = now;
    return entry;
  }

  /** An entry untouched for an idle hour belongs to a session that has expired: it is dropped, tokens and all. */
  private sweep(now: number): void {
    if (now - this.swept < 60_000) return;
    this.swept = now;
    for (const [key, entry] of this.entries) {
      if (entry.inflight === undefined && now - entry.touched > IDLE_SECONDS * 1000) this.entries.delete(key);
    }
  }

  async tokenFor(record: SessionRecord, hooks: RenewalHooks): Promise<string> {
    const entry = this.entryFor(record);
    const finish = async (reason: EndReason): Promise<never> => {
      await hooks.end(reason);
      throw new SessionEnded(reason, this.deps.now() - record.createdAt < RECENT_SIGN_IN_SECONDS * 1000);
    };
    if (entry.ended !== undefined) return finish(entry.ended);

    this.bringUpToDate(entry, record);
    const now = this.deps.now();
    const expiresAt = expiryOf(record);
    // Not dated, or not near its end: nothing to do.
    if (expiresAt === undefined || expiresAt - now > RENEWAL_MARGIN_SECONDS * 1000) return record.accessToken;
    const expired = expiresAt <= now;

    // Nothing to renew with, or a token that may already be spent: the token held is used while it is good, and no longer.
    if (record.refreshToken === "" || entry.spent === true) {
      return expired ? finish(record.refreshToken === "" ? "no_refresh_token" : "unavailable") : record.accessToken;
    }
    // The provider could not be reached a moment ago: not asked again yet.
    if (entry.coolOffUntil !== undefined && now < entry.coolOffUntil) {
      return expired ? finish("unavailable") : record.accessToken;
    }

    // One exchange at a time for a session: the first caller makes it, the others wait for it.
    entry.inflight ??= this.exchange(entry, record, hooks).finally(() => {
      entry.inflight = undefined;
    });
    const outcome = await entry.inflight;
    switch (outcome.kind) {
      case "renewed":
        this.bringUpToDate(entry, record);
        return record.accessToken;
      case "refused":
        return finish("refused");
      case "unavailable":
        return expired ? finish("unavailable") : record.accessToken;
      case "unexpected":
        return finish("unexpected");
    }
  }

  /** Brings a copy of the record up to the newest renewal this process has made for its session. */
  private bringUpToDate(entry: Entry, record: SessionRecord): void {
    const latest = entry.latest;
    if (latest === undefined || (record.renewals ?? 0) >= latest.renewals) return;
    record.accessToken = latest.accessToken;
    record.refreshToken = latest.refreshToken;
    record.renewals = latest.renewals;
    if (latest.accessTokenExpiresAt === undefined) delete record.accessTokenExpiresAt;
    else record.accessTokenExpiresAt = latest.accessTokenExpiresAt;
    if (latest.idToken !== undefined) record.idToken = latest.idToken;
    if (latest.idpSessionExpiresAt !== undefined) record.idpSessionExpiresAt = latest.idpSessionExpiresAt;
  }

  private async exchange(entry: Entry, record: SessionRecord, hooks: RenewalHooks): Promise<Outcome> {
    const presented = record.refreshToken;
    for (let attempt = 0; ; attempt += 1) {
      try {
        const renewed = await this.deps.refresh(presented);
        entry.latest = {
          renewals: Math.max(record.renewals ?? 0, entry.latest?.renewals ?? 0) + 1,
          accessToken: renewed.accessToken,
          accessTokenExpiresAt: renewed.accessTokenExpiresAt,
          refreshToken: renewed.refreshToken ?? presented,
          idToken: renewed.idToken,
          idpSessionExpiresAt: renewed.idpSessionExpiresAt,
        };
        entry.coolOffUntil = undefined;
        this.bringUpToDate(entry, record);
        // Kept now, not at the end of the response: a renewal is the one write a crash must not lose.
        await hooks.persist().catch(() => {
          this.deps.log("pages: renewal: the renewed session could not be saved");
        });
        return { kind: "renewed" };
      } catch (error) {
        if (error instanceof IdentityProviderRefused) {
          entry.ended = "refused";
          entry.latest = undefined;
          return { kind: "refused" };
        }
        if (error instanceof IdentityProviderUnavailable) {
          if (error.notDelivered && attempt < this.backoff.length) {
            await this.sleep(this.backoff[attempt] as number);
            continue;
          }
          entry.coolOffUntil = this.deps.now() + UNREACHABLE_COOL_OFF_SECONDS * 1000;
          if (!error.notDelivered) entry.spent = true;
          this.deps.log(`pages: renewal: the identity provider could not be reached or failed (${error.notDelivered ? "not received" : "may have been received"})`);
          return { kind: "unavailable", spent: !error.notDelivered };
        }
        // Not the provider's doing and not ours to describe: the token may have been presented, so it is not presented again.
        entry.spent = true;
        this.deps.log("pages: renewal: unexpected failure");
        return { kind: "unexpected" };
      }
    }
  }
}

export function createRenewal(deps: RenewalDeps): Renewal {
  return new RenewalImpl(deps);
}
