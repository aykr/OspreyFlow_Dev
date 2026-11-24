/**
 * Slice PL9b, acceptance, first half: the page service renews the person's access token, and ends the session cleanly when the
 * identity provider will not (ADR-152 decisions 4 and 5, ADR-050 Amendment 4 point 3, ADR-044).
 *
 * Every case drives the real app over real HTTP (supertest) against a fake Keycloak that REFUSES what the real one refuses
 * (`test/support/fakeKeycloak.ts`, `CLAUDE.md` rule 15): a refresh grant with a wrong client secret, a missing, unknown, ended
 * or already-used refresh token, a session ended at the provider. With rotation on (the strictest a realm can be set to) a
 * refresh token presented a second time revokes the person's whole session at the provider, so two exchanges with one
 * token cannot pass here. The Conduit is a fake that accepts only a bearer the provider issued and that has not ended by the
 * provider's clock. Tokens and secrets are made when the test runs.
 *
 * Which test fails if the behaviour is wrong (rule 12):
 * - no renewal at all (the stub): "renews with the refresh token ...": the Conduit refuses the expired bearer and the session
 *   never holds a second set of tokens;
 * - a margin that is not the named one: "does not exchange while the token has more than the margin left, and does at it";
 * - the session not updated (the new token used once, the old one kept): "renews with the refresh token ..." reads the store;
 * - two exchanges with one refresh token: "eight requests at once make one exchange": the fake revokes the session on reuse,
 *   so the second exchange ends it and every request after fails; and "a request that read the session before the renewal ...";
 * - a refusal that does not end the session, or a loop of redirects, or the old token sent again: the table "each refusal
 *   ends the session cleanly" (page, script and form request each; the Conduit sees no call; the refresh token is not
 *   presented again);
 * - an unreachable provider told as a refusal at once, or the reverse: "a provider that cannot be reached ...";
 * - a token, the refresh token, the client secret or the provider's own words in a response or a log: the leak scan on every
 *   refusal, with a marker in the provider's `error_description`;
 * - a fake that grants what Keycloak refuses: "the fake provider refuses what Keycloak refuses at the refresh grant".
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_BACKOFF_MS, RENEWAL_MARGIN_SECONDS, accessTokenFor, createRenewal } from "../../server/accessToken.js";
import type { SessionRecord } from "../../server/sessionPolicy.js";
import { SESSION_KEY_PREFIX } from "../../server/sessionStore.js";
import type { SessionStore } from "../../server/sessionStore.js";
import { captureOutput } from "../support/capture.js";
import { everythingIn, idFrom, request, setCookies } from "../support/http.js";
import { CLIENT_ID, clearsSessionCookie, csrfOf, expectNoSecret, rig, signInAs, stopRigs } from "../support/providerRig.js";
import type { Person, Rig } from "../support/providerRig.js";
import { generateSecret } from "../support/secret.js";

vi.setConfig({ testTimeout: 30_000 });
afterEach(stopRigs);

/** The margin and the access token's life in these cases: the numbers the brief names, written here and not imported. */
const MARGIN = 60;
const LIFE = 300;
const ENDED_WORDS = "You are not signed in, or your session has ended. Sign in again.";
const REFUSED_WORDS = "Sign-in was refused. Nothing about your access has changed.";

function sessionKeys(r: Rig): string[] {
  return r.store.keys().filter((key) => key.startsWith(SESSION_KEY_PREFIX));
}

async function authOf(r: Rig, person: Pick<Person, "id">): Promise<Record<string, unknown>> {
  const raw = await r.store.get(`${SESSION_KEY_PREFIX}${person.id}`);
  if (raw === null) throw new Error("the session is not in the store");
  return (JSON.parse(raw) as { auth: Record<string, unknown> }).auth;
}

async function editSession(r: Rig, person: Pick<Person, "id">, change: (auth: Record<string, unknown>) => void): Promise<void> {
  const key = `${SESSION_KEY_PREFIX}${person.id}`;
  const parsed = JSON.parse((await r.store.get(key)) as string) as { auth: Record<string, unknown> };
  change(parsed.auth);
  await r.store.set(key, JSON.stringify(parsed), 600);
}

/** The next `/v1` call as the person's script makes it. */
function callConduit(r: Rig, person: Pick<Person, "cookie">): Promise<{ status: number; body: unknown; res: Awaited<ReturnType<ReturnType<typeof request>["get"]>> }> {
  return request(r.app)
    .get("/v1/me")
    .set("Cookie", person.cookie)
    .then((res) => ({ status: res.status, body: res.body as unknown, res }));
}

describe("the margin", () => {
  it("is a named constant of sixty seconds", () => {
    expect(RENEWAL_MARGIN_SECONDS).toBe(MARGIN);
  });

  it("does not exchange while the token has more than the margin left, and does at it", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const first = r.fake.issued[0]!;

    r.advance(LIFE - MARGIN - 1); // sixty-one seconds left
    const before = await callConduit(r, person);
    expect(before.status).toBe(200);
    expect(r.fake.refreshCalls, "no exchange with more than the margin left").toBe(0);
    expect(r.upstream.calls.at(-1)?.bearer).toBe(first.accessToken);

    r.advance(1); // exactly the margin left
    const at = await callConduit(r, person);
    expect(at.status).toBe(200);
    expect(r.fake.refreshCalls, "one exchange at the margin").toBe(1);
    expect(r.upstream.calls.at(-1)?.bearer).toBe(r.fake.issued[1]!.accessToken);
  });
});

describe("renewal", () => {
  it("renews with the refresh token, updates the session and sends the new token, with the same cookie", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const [first] = r.fake.issued as [(typeof r.fake.issued)[number]];
    r.advance(LIFE - MARGIN);

    const res = await callConduit(r, person);
    expect(res.status).toBe(200);
    expect(r.fake.refreshes).toEqual([{ refreshToken: first.refreshToken, status: 200 }]);
    const renewed = r.fake.issued[1]!;
    expect(r.upstream.calls.map((c) => [c.bearer, c.status])).toEqual([[renewed.accessToken, 200]]);

    // The session record is updated: the new access token and its end, the rotated refresh token, the provider's session end.
    const auth = await authOf(r, person);
    expect(auth["accessToken"]).toBe(renewed.accessToken);
    expect(auth["refreshToken"]).toBe(renewed.refreshToken);
    expect(auth["accessTokenExpiresAt"]).toBe(r.clock() + LIFE * 1000);
    expect(auth["idpSessionExpiresAt"]).toBe(r.clock() + 1800 * 1000);
    expect(JSON.stringify(auth), "the spent refresh token is not kept").not.toContain(first.refreshToken);
    expect(JSON.stringify(auth), "nor the old access token").not.toContain(first.accessToken);

    // The browser's cookie is the same one, and nothing of the exchange reached it.
    const ids = setCookies(res.res).filter((c) => c.startsWith("osprey_pages=") && !/^osprey_pages=;/.test(c));
    for (const cookie of ids) expect(idFrom({ headers: { "set-cookie": cookie } })).toBe(person.id);
    expectNoSecret(r, everythingIn(res.res), "the response");

    // The next call in the new window is not another exchange; the one after the next window uses the rotated token.
    await callConduit(r, person);
    expect(r.fake.refreshCalls).toBe(1);
    r.advance(LIFE - MARGIN);
    expect((await callConduit(r, person)).status).toBe(200);
    expect(r.fake.refreshes.map((x) => x.refreshToken)).toEqual([first.refreshToken, renewed.refreshToken]);
    expect(r.fake.refreshes.map((x) => x.status)).toEqual([200, 200]);
  });

  it("renews before a page request runs, as it does before a script's", async () => {
    const r = await rig();
    const person = await signInAs(r);
    r.advance(LIFE - MARGIN);
    const page = await request(r.app).get("/").set("Cookie", person.cookie);
    expect(page.status).toBe(200);
    expect(r.fake.refreshCalls).toBe(1);
    expect((await authOf(r, person))["accessToken"]).toBe(r.fake.issued[1]!.accessToken);
  });

  it.each([
    ["rotation is off", { rotateRefreshTokens: false }, false],
    ["rotation is off and the answer names no refresh token", { rotateRefreshTokens: false }, true],
  ])("keeps the refresh token as it was when %s", async (_name, fakeOptions, omit) => {
    const r = await rig({ fake: fakeOptions });
    r.fake.refreshOmitRefreshToken = omit;
    const person = await signInAs(r);
    const original = r.fake.issued[0]!.refreshToken;
    r.advance(LIFE - MARGIN);
    expect((await callConduit(r, person)).status).toBe(200);
    expect((await authOf(r, person))["refreshToken"]).toBe(original);
    r.advance(LIFE - MARGIN);
    expect((await callConduit(r, person)).status).toBe(200);
    expect(r.fake.refreshes.map((x) => x.status)).toEqual([200, 200]);
  });

  it("does not renew at sign-out: a person leaving is not made to wait for a token", async () => {
    const r = await rig();
    const person = await signInAs(r);
    const csrf = await csrfOf(r, person);
    r.advance(LIFE - MARGIN);
    const out = await request(r.app).post("/session/sign-out").set("Cookie", person.cookie).type("form").send({ _csrf: csrf });
    expect(out.status).toBe(303);
    expect(r.fake.refreshCalls).toBe(0);
    expect(sessionKeys(r)).toEqual([]);
  });
});

describe("single flight", () => {
  it("eight requests at once make one exchange, and each carries the new token", async () => {
    const r = await rig();
    const person = await signInAs(r);
    r.advance(LIFE - MARGIN);
    const results = await Promise.all(Array.from({ length: 8 }, () => callConduit(r, person)));
    expect(results.map((x) => x.status)).toEqual(Array(8).fill(200));
    expect(r.fake.refreshCalls, "one exchange, not eight").toBe(1);
    expect(r.fake.refreshes.map((x) => x.status)).toEqual([200]);
    const renewed = r.fake.issued[1]!;
    expect(r.upstream.calls.map((c) => c.bearer)).toEqual(Array(8).fill(renewed.accessToken));
    expect(sessionKeys(r), "the session is alive: the provider did not revoke it").toEqual([`${SESSION_KEY_PREFIX}${person.id}`]);
    expect((await authOf(r, person))["refreshToken"]).toBe(renewed.refreshToken);
    expect(r.fake.sessions.get(person.sid)?.ended).toBe(false);
  });

  it("is one exchange for each session, not one for the service", async () => {
    const r = await rig();
    const one = await signInAs(r);
    const two = await signInAs(r);
    r.advance(LIFE - MARGIN);
    const results = await Promise.all([one, two, one, two, one, two].map((p) => callConduit(r, p)));
    expect(results.map((x) => x.status)).toEqual(Array(6).fill(200));
    expect(r.fake.refreshCalls).toBe(2);
    expect(new Set(r.fake.refreshes.map((x) => x.refreshToken)).size, "two different refresh tokens").toBe(2);
    expect(r.fake.refreshes.every((x) => x.status === 200)).toBe(true);
  });

  it("a request that read the session before the renewal does not exchange the spent token again", async () => {
    let stale: string | undefined;
    let serveStale = false;
    const r = await rig({
      wrapStore: (inner): SessionStore =>
        Object.create(inner, {
          get: {
            value: async (key: string): Promise<string | null> => {
              if (serveStale && stale !== undefined && key.startsWith(SESSION_KEY_PREFIX)) return stale;
              return inner.get(key);
            },
          },
        }) as SessionStore,
    });
    const person = await signInAs(r);
    stale = (await r.store.get(`${SESSION_KEY_PREFIX}${person.id}`)) as string;
    r.advance(LIFE - MARGIN);
    expect((await callConduit(r, person)).status).toBe(200);
    expect(r.fake.refreshCalls).toBe(1);

    // The next request is handed the record as it was before the renewal: the old tokens, and a margin already crossed.
    serveStale = true;
    const late = await callConduit(r, person);
    serveStale = false;
    expect(late.status).toBe(200);
    expect(r.fake.refreshCalls, "the spent refresh token is not presented again").toBe(1);
    expect(r.upstream.calls.at(-1)?.bearer).toBe(r.fake.issued[1]!.accessToken);
    expect(r.fake.sessions.get(person.sid)?.ended, "the provider did not revoke the session").toBe(false);
    expect((await callConduit(r, person)).status).toBe(200);
    expect((await authOf(r, person))["refreshToken"]).toBe(r.fake.issued[1]!.refreshToken);
  });
});

describe("accessTokenFor on its own", () => {
  const NOW = Date.UTC(2026, 10, 24, 9, 0, 0);
  const record = (): SessionRecord => ({
    v: 1,
    subject: "sub-alex",
    displayName: "Alex",
    accessToken: "access-0",
    refreshToken: "refresh-0",
    csrfToken: "csrf-of-this-session",
    createdAt: NOW - 600_000,
    idpSessionExpiresAt: NOW + 1_800_000,
    accessTokenExpiresAt: NOW + 30_000, // inside the margin
  });
  const hooks = { persist: () => Promise.resolve(), end: () => Promise.resolve() };

  it("hands every caller of one session the new token from the call itself, after one exchange", async () => {
    const presented: string[] = [];
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const renewal = createRenewal({
      now: () => NOW,
      log: () => undefined,
      refresh: async (token) => {
        presented.push(token);
        await gate;
        return { accessToken: "access-1", refreshToken: "refresh-1", accessTokenExpiresAt: NOW + 300_000 };
      },
    });
    // Three copies of one session, as three requests each load their own.
    const copies = [record(), record(), record()];
    for (const copy of copies) renewal.bind(copy, hooks);
    const calls = copies.map((copy) => accessTokenFor(copy));
    release();
    expect(await Promise.all(calls)).toEqual(["access-1", "access-1", "access-1"]);
    expect(presented, "one exchange, with the token the session held").toEqual(["refresh-0"]);
    for (const copy of copies) {
      expect(copy.refreshToken).toBe("refresh-1");
      expect(copy.accessTokenExpiresAt).toBe(NOW + 300_000);
    }
    // A copy read before the exchange, asked afterwards, is brought up to date and not exchanged for.
    const late = record();
    renewal.bind(late, hooks);
    expect(await accessTokenFor(late)).toBe("access-1");
    expect(presented).toEqual(["refresh-0"]);
    expect(late.refreshToken).toBe("refresh-1");
  });

  it("returns a record that no request has bound as it is, and exchanges nothing", async () => {
    const lone = record();
    expect(await accessTokenFor(lone)).toBe("access-0");
    expect(lone.refreshToken).toBe("refresh-0");
  });
});

/** One way the provider says no (or cannot be asked), and what the service then did. */
interface Refusal {
  name: string;
  /** Changes how the fake or the world answers; runs after sign-in, before the clock moves. */
  cause(r: Rig, people: Person[]): Promise<void> | void;
  /** Seconds to move both clocks: the margin by default; past the token's end for a provider that cannot be reached. */
  advance?: number;
  rig?: Parameters<typeof rig>[0];
  /** Exchanges the service makes for each person: one for a plain refusal. */
  attempts: number;
  /** The fixed class the service logs. */
  class: string;
}

const REFUSALS: Refusal[] = [
  {
    name: "the refresh token has ended at the provider (invalid_grant: Token is not active)",
    rig: { fake: { refreshEnforcedSeconds: 100 } },
    cause: () => undefined,
    attempts: 1,
    class: "refused",
  },
  {
    name: "the provider's session has ended, signed out elsewhere (invalid_grant: Session not active)",
    cause: (r, people) => {
      for (const p of people) r.fake.endSession(p.sid);
    },
    attempts: 1,
    class: "refused",
  },
  {
    name: "the refresh token was already spent by another holder (reuse: the provider revokes the family)",
    cause: async (r, people) => {
      for (const p of people) {
        const held = (await authOf(r, p))["refreshToken"] as string;
        const spend = await fetch(`${r.fake.issuer}/protocol/openid-connect/token`, {
          method: "POST",
          headers: { "content-type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: held, client_id: CLIENT_ID, client_secret: r.clientSecret }),
        });
        expect(spend.status).toBe(200);
      }
    },
    attempts: 1,
    class: "refused",
  },
  {
    name: "the client's secret was changed at the provider (401 invalid_client)",
    cause: (r) => {
      r.fake.clientSecret = generateSecret();
    },
    attempts: 1,
    class: "refused",
  },
  {
    name: "the answer is a 200 that leaves the access token out",
    cause: (r) => {
      r.fake.refreshOmitAccessToken = true;
    },
    attempts: 1,
    class: "refused",
  },
  {
    name: "the answer is a 200 that is a web page, not a token response",
    cause: (r) => {
      r.fake.refreshBody = "<html><body>Down for maintenance</body></html>";
    },
    attempts: 1,
    class: "refused",
  },
  {
    name: "the answer is a 200 with an empty object",
    cause: (r) => {
      r.fake.refreshBody = "{}";
    },
    attempts: 1,
    class: "refused",
  },
  {
    name: "the refresh token held is not one the provider made (invalid_grant: Invalid refresh token)",
    cause: async (r, people) => {
      for (const p of people) await editSession(r, p, (auth) => (auth["refreshToken"] = "not-a-token-of-the-providers"));
    },
    attempts: 1,
    class: "refused",
  },
  {
    name: "the session holds no refresh token and the access token has ended, so there is nothing to renew with",
    advance: LIFE + 1,
    cause: async (r, people) => {
      for (const p of people) await editSession(r, p, (auth) => (auth["refreshToken"] = ""));
    },
    attempts: 0,
    class: "no_refresh_token",
  },
  {
    name: "the provider cannot be reached and the access token has ended",
    advance: LIFE + 1,
    cause: (r) => r.fake.stop(),
    attempts: 0,
    class: "unavailable",
  },
  {
    name: "the provider answers 503, never having seen the request, and the access token has ended: tried three times",
    advance: LIFE + 1,
    cause: (r) => {
      r.fake.refreshStatus = 503;
    },
    attempts: 3,
    class: "unavailable",
  },
  {
    name: "the provider answers 500, which may have spent the token, and the access token has ended: tried once",
    advance: LIFE + 1,
    cause: (r) => {
      r.fake.refreshStatus = 500;
    },
    attempts: 1,
    class: "unavailable",
  },
];

describe("each refusal ends the session cleanly", () => {
  it.each(REFUSALS)("$name", async (refusal) => {
    const sleeps: number[] = [];
    const r = await rig({
      ...refusal.rig,
      renewal: {
        sleep: (ms) => {
          sleeps.push(ms);
          return Promise.resolve();
        },
      },
    });
    // The provider's own words carry a marker, which must reach no response and no log.
    const marker = `PROVIDER-WORDS-${generateSecret().slice(0, 12)}`;
    r.fake.refusalDescription = marker;
    // Three sessions, so that a page, a script and a form each meet the refusal.
    const people = [await signInAs(r), await signInAs(r), await signInAs(r)] as [Person, Person, Person];
    const [pagePerson, scriptPerson, formPerson] = people;
    const csrf = await csrfOf(r, formPerson);
    await refusal.cause(r, people);
    const callsBefore = r.fake.refreshCalls;
    const captured = captureOutput();
    const responses: Awaited<ReturnType<typeof callConduit>>["res"][] = [];
    let page, script, form;
    try {
      r.advance(refusal.advance ?? LIFE - MARGIN);
      page = await request(r.app).get("/_test/echo?x=1").set("Cookie", pagePerson.cookie);
      script = await callConduit(r, scriptPerson);
      form = await request(r.app).post("/_test/echo").set("Cookie", formPerson.cookie).type("form").send({ _csrf: csrf });
      responses.push(page, script.res, form);
    } finally {
      captured.restore();
    }

    // A page request is sent to sign in again, at the address it came from; a form post, which cannot be asked for again, to the start.
    expect(page.status).toBe(302);
    expect(page.headers["location"]).toBe("/session/sign-in?returnTo=%2F_test%2Fecho%3Fx%3D1");
    expect(form.status).toBe(303);
    expect(form.headers["location"]).toBe("/session/sign-in");
    // A script's call is answered 401 in the forwarder's own words, with no redirect.
    expect(script.status).toBe(401);
    expect(script.body).toEqual({ detail: ENDED_WORDS });
    expect(script.res.headers["location"]).toBeUndefined();
    // Every one cleared the cookie, ended the session and said it must not be kept.
    for (const res of responses) {
      expect(clearsSessionCookie(res), "the cookie is cleared").toBe(true);
      expect(res.headers["cache-control"]).toBe("no-store");
    }
    expect(sessionKeys(r), "no session is left").toEqual([]);

    // The old token was never sent again, and the Conduit was never reached.
    expect(r.upstream.calls, "nothing was sent to the Conduit").toEqual([]);
    // The provider was asked as often as the design says, and never twice with one token.
    expect(r.fake.refreshCalls - callsBefore).toBe(refusal.attempts * 3);
    const presented = r.fake.refreshes.slice(callsBefore).map((x) => x.refreshToken);
    for (const person of people) {
      const own = presented.filter((token) => token === (r.fake.issued[person.issuedAt]?.refreshToken ?? "(none)"));
      expect(own.length, "attempts per person").toBeLessThanOrEqual(refusal.attempts);
    }
    if (refusal.class === "unavailable" && refusal.attempts === 3) expect(sleeps.slice(0, 2)).toEqual([...DEFAULT_BACKOFF_MS]);
    if (refusal.attempts === 3) expect(DEFAULT_BACKOFF_MS.reduce((a, b) => a + b, 0), "a short time").toBeLessThanOrEqual(2000);

    // The browser that did not clear its cookie, and comes back: no session, no call, no further exchange.
    const exchanges = r.fake.refreshCalls;
    const stale = await callConduit(r, scriptPerson);
    expect(stale.status).toBe(401);
    expect(stale.body).toEqual({ detail: ENDED_WORDS });
    expect(r.upstream.calls).toEqual([]);
    expect(r.fake.refreshCalls, "no exchange for a session that is gone").toBe(exchanges);

    // No loop: where the redirect leads is the start of a sign-in at the provider, not the page again.
    const followed = await request(r.app).get(page.headers["location"] as string);
    expect(followed.status).toBe(302);
    expect(new URL(followed.headers["location"] as string).origin + new URL(followed.headers["location"] as string).pathname).toBe(
      `${r.fake.issuer}/protocol/openid-connect/auth`,
    );

    // Nothing of a token, the refresh token, the client's secret or the provider's words in what was said or logged.
    for (const res of responses) {
      expectNoSecret(r, everythingIn(res), "a response", [marker]);
    }
    expectNoSecret(r, captured.text(), "the console", [marker]);
    expectNoSecret(r, r.log.join("\n"), "the log", [marker]);
    const ended = r.log.filter((line) => line.startsWith("pages: session ended: "));
    expect(ended.length, "each ended session says so, once").toBe(3);
    for (const line of ended) expect(line).toBe(`pages: session ended: ${refusal.class}`);
  });

  it("a session signed in moments ago and refused at once is told so, not sent round again", async () => {
    // An access token that is due as it is issued (thirty seconds, inside the margin) and a provider that then says no: a
    // redirect would sign the person in and refuse again without end.
    const r = await rig({ fake: { accessTokenSeconds: 30 } });
    const person = await signInAs(r);
    r.fake.clientSecret = generateSecret();
    r.advance(5);
    const page = await request(r.app).get("/_test/echo").set("Cookie", person.cookie);
    expect(page.status).toBe(403);
    expect(page.text).toContain(REFUSED_WORDS);
    expect(page.headers["location"]).toBeUndefined();
    expect(clearsSessionCookie(page)).toBe(true);
    expect(sessionKeys(r)).toEqual([]);
    expectNoSecret(r, everythingIn(page), "the page");
  });
});

describe("a provider that cannot be reached is not an ended session while the token is good", () => {
  it.each([
    ["is not running", 0, (r: Rig): Promise<void> => r.fake.stop()],
    ["answers 503", 3, (r: Rig): Promise<void> => Promise.resolve(void (r.fake.refreshStatus = 503))],
  ] as const)("when it %s, the token still held is used, and the exchange is tried again later", async (_name, attempts, cause) => {
    const sleeps: number[] = [];
    const r = await rig({
      renewal: {
        sleep: (ms: number): Promise<void> => {
          sleeps.push(ms);
          return Promise.resolve();
        },
      },
    });
    const person = await signInAs(r);
    const held = r.fake.issued[0]!;
    await cause(r);
    r.advance(LIFE - MARGIN); // inside the margin, not yet ended

    const during = await callConduit(r, person);
    expect(during.status).toBe(200);
    expect(r.upstream.calls.at(-1)?.bearer, "the token still held, which is still good").toBe(held.accessToken);
    expect(clearsSessionCookie(during.res)).toBe(false);
    expect(sessionKeys(r)).toEqual([`${SESSION_KEY_PREFIX}${person.id}`]);
    expect(r.fake.refreshCalls).toBe(attempts);
    expect(sleeps.length, "retried with a pause, a short time").toBe(2);

    // A cool-off: the next request does not try again, or every request would wait out the retries.
    const calls = r.fake.refreshCalls;
    await callConduit(r, person);
    expect(r.fake.refreshCalls).toBe(calls);
  });

  it("recovers: when the provider is back after the cool-off the token is renewed and the session goes on", async () => {
    const r = await rig({ renewal: { sleep: () => Promise.resolve() } });
    const person = await signInAs(r);
    r.fake.refreshStatus = 503;
    r.advance(LIFE - MARGIN);
    expect((await callConduit(r, person)).status).toBe(200);
    r.fake.refreshStatus = undefined;
    r.advance(11); // past the cool-off, and the token still has life
    const back = await callConduit(r, person);
    expect(back.status).toBe(200);
    expect(r.upstream.calls.at(-1)?.bearer).toBe(r.fake.issued[1]!.accessToken);
    expect(r.fake.refreshes.at(-1)?.status).toBe(200);
  });

  it("a refresh that may have been received is not tried again with the same token, and the session ends when the token does", async () => {
    const r = await rig({ renewal: { sleep: () => Promise.resolve() } });
    const person = await signInAs(r);
    r.fake.refreshStatus = 500; // the provider failed after reading the request: the token may be spent
    r.advance(LIFE - MARGIN);
    expect((await callConduit(r, person)).status).toBe(200);
    expect(r.fake.refreshCalls).toBe(1);

    r.fake.refreshStatus = undefined; // the provider recovers, but the token's fate is unknown: it is not presented again
    r.advance(11);
    expect((await callConduit(r, person)).status).toBe(200);
    expect(r.fake.refreshCalls, "the possibly spent token is not presented again").toBe(1);

    r.advance(LIFE); // the access token has now ended
    const ended = await callConduit(r, person);
    expect(ended.status).toBe(401);
    expect(clearsSessionCookie(ended.res)).toBe(true);
    expect(sessionKeys(r)).toEqual([]);
    expect(r.fake.refreshCalls).toBe(1);
  });
});

describe("the fake provider refuses what Keycloak refuses at the refresh grant (rule 15)", () => {
  async function grant(r: Rig, form: Record<string, string>, basic?: string): Promise<{ status: number; body: Record<string, unknown> }> {
    const res = await fetch(`${r.fake.issuer}/protocol/openid-connect/token`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", ...(basic ? { authorization: `Basic ${basic}` } : {}) },
      body: new URLSearchParams(form),
    });
    return { status: res.status, body: (await res.json()) as Record<string, unknown> };
  }

  it("refuses a wrong client, a missing token, a token it did not make, an access token, a spent token and an ended session", async () => {
    const r = await rig();
    await signInAs(r);
    const issued = r.fake.issued[0]!;
    const base = { grant_type: "refresh_token", client_id: CLIENT_ID };
    const ok = { ...base, client_secret: r.clientSecret };

    expect(await grant(r, { ...base, refresh_token: issued.refreshToken, client_secret: generateSecret() })).toMatchObject({ status: 401, body: { error: "invalid_client" } });
    expect(await grant(r, { ...base, refresh_token: issued.refreshToken })).toMatchObject({ status: 401, body: { error: "invalid_client" } });
    expect(await grant(r, { ...ok })).toMatchObject({ status: 400, body: { error: "invalid_request" } });
    expect(await grant(r, { ...ok, refresh_token: "garbage" })).toMatchObject({ status: 400, body: { error: "invalid_grant" } });
    expect(await grant(r, { ...ok, refresh_token: issued.accessToken }), "an access token is not a refresh token").toMatchObject({
      status: 400,
      body: { error: "invalid_grant" },
    });
    expect(await grant(r, { ...ok, grant_type: "password" })).toMatchObject({ status: 400 });

    // Granted once; the same token a second time revokes the family, and so the new token is refused too.
    const first = await grant(r, { ...ok, refresh_token: issued.refreshToken });
    expect(first.status).toBe(200);
    expect(typeof first.body["access_token"]).toBe("string");
    expect(await grant(r, { ...ok, refresh_token: issued.refreshToken })).toMatchObject({
      status: 400,
      body: { error: "invalid_grant", error_description: "Maximum allowed refresh token reuse exceeded" },
    });
    expect(await grant(r, { ...ok, refresh_token: first.body["refresh_token"] as string })).toMatchObject({
      status: 400,
      body: { error: "invalid_grant", error_description: "Session not active" },
    });
  });

  it("refuses a token that has ended, and a session that has ended", async () => {
    const r = await rig({ fake: { rotateRefreshTokens: false } });
    await signInAs(r);
    const ok = { grant_type: "refresh_token", client_id: CLIENT_ID, client_secret: r.clientSecret };
    const issued = r.fake.issued[0]!;
    expect((await grant(r, { ...ok, refresh_token: issued.refreshToken })).status).toBe(200);
    expect((await grant(r, { ...ok, refresh_token: issued.refreshToken })).status, "reuse is allowed when rotation is off").toBe(200);
    r.fake.endSession(issued.sid);
    expect(await grant(r, { ...ok, refresh_token: issued.refreshToken })).toMatchObject({ status: 400, body: { error_description: "Session not active" } });
    const later = await rig();
    await signInAs(later);
    later.fake.advance(1801);
    expect(
      await grant(later, { grant_type: "refresh_token", client_id: CLIENT_ID, client_secret: later.clientSecret, refresh_token: later.fake.issued[0]!.refreshToken }),
    ).toMatchObject({ status: 400, body: { error: "invalid_grant", error_description: "Token is not active" } });
  });
});
