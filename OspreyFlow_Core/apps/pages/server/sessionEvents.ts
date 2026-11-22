/**
 * The page service reports a person's sign-in and sign-out to the Conduit (SE8c; `RULINGS.md` SE8: "sign-ins are
 * recorded by the product, with no change to any identity provider's configuration").
 *
 * WHAT IS SENT. `POST {conduit}/v1/session-events` with the person's own access token as the bearer (the one
 * `accessTokenFor` names), `Content-Type: application/json` and a body of one field, `{"kind": "sign_in"}` or
 * `{"kind": "sign_out"}`. Nothing else: no cookie, no session identifier, no anti-forgery token, no refresh token,
 * no ID token, no code, no state, no client secret, no address of the provider. The Conduit validates the token
 * itself and records the event for the person the token names and no one else; it accepts no word from here.
 *
 * WHAT IS NEVER STOPPED. A sign-in and a sign-out never wait for this and are never stopped by it: the call is
 * made after the session is saved (or deleted), not awaited by the response, bounded by a time limit, and any
 * failure is a miss (`misses`) and a log line of fixed words and a status, never an error's own message and
 * never the token. A Conduit that is down, silent, or refuses (401 for a token that has expired, 429, 5xx) costs
 * a log line and a count. A redirect is never followed: the bearer goes to the configured Conduit and nowhere else.
 *
 * WHAT IS NOT REPORTED. A refused sign-in: the provider refused before there was a token, so nothing reaches the
 * Conduit, and the attempt stays in the identity provider's own log.
 */

export const SESSION_EVENT_PATH = "/v1/session-events";

/** Seconds the Conduit gets to answer one report before it is given up. */
export const DEFAULT_SESSION_EVENT_TIMEOUT_MS = 3000;

export type SessionEventKind = "sign_in" | "sign_out";

export interface SessionEventReporter {
  /** Reports one event. Never rejects: a failure is a miss and a log line. */
  report(kind: SessionEventKind, token: string): Promise<void>;
  /** Resolves when every report started so far has ended (a test waits on it; the service does not). */
  settled(): Promise<void>;
  /** Reports that could not be made or were refused. */
  readonly misses: number;
}

export interface SessionEventOptions {
  /** The Conduit's address: scheme, host and port, no path (`OSPREY_PAGES_CONDUIT_URL`). */
  conduitUrl: string;
  log: (message: string) => void;
  timeoutMs?: number;
}

export function createSessionEventReporter(options: SessionEventOptions): SessionEventReporter {
  const target = `${options.conduitUrl.replace(/\/+$/, "")}${SESSION_EVENT_PATH}`;
  const timeoutMs = options.timeoutMs ?? DEFAULT_SESSION_EVENT_TIMEOUT_MS;
  const inFlight = new Set<Promise<void>>();
  let misses = 0;

  const miss = (kind: SessionEventKind, why: string): void => {
    misses += 1;
    // Fixed words and a status: never the token, the Conduit's own words, or an error's message.
    options.log(`pages: session event not recorded: ${kind}: ${why}`);
  };

  async function send(kind: SessionEventKind, token: string): Promise<void> {
    try {
      const response = await fetch(target, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ kind }),
        redirect: "error",
        signal: AbortSignal.timeout(timeoutMs),
      });
      await response.body?.cancel().catch(() => undefined);
      if (response.status >= 200 && response.status < 300) return;
      miss(kind, response.status === 401 ? "the Conduit did not accept the sign-in (401)" : `the Conduit answered ${response.status}`);
    } catch (error) {
      const timedOut = error instanceof DOMException && (error.name === "TimeoutError" || error.name === "AbortError");
      miss(kind, timedOut ? "the Conduit did not answer in time" : "the Conduit could not be reached");
    }
  }

  return {
    report(kind, token) {
      const started = send(kind, token).catch(() => {
        misses += 1;
      });
      inFlight.add(started);
      void started.finally(() => inFlight.delete(started));
      return started;
    },
    async settled() {
      while (inFlight.size > 0) await Promise.all([...inFlight]);
    },
    get misses() {
      return misses;
    },
  };
}
