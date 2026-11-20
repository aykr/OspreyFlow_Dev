/**
 * Slice PL9a, round 2: the realm's key set failing after the code was spent (ADR-044).
 *
 * The ID token's signature is checked against the realm's key set, which is first fetched by the first sign-in
 * after a start or a key rotation, that is after the code exchange has already succeeded. The realm failing there
 * (a 500, a gateway's 502 while it restarts, a body that is not a key set) is the provider failing, not the
 * provider saying no: `503`, not `403` (ADR-044, brief: "IdentityProviderUnavailable stays 503"). A token that
 * merely does not verify stays a `403`.
 *
 * Which test fails if the flow returns the wrong thing (rule 12):
 * - a key-set failure told as a refusal: "a key set that answers 500 / 502 / not a key set is a 503";
 * - a verification failure told as unavailable: "a token signed by another key is still a refusal".
 *
 * The fake models this refusal on purpose (`certsStatus`, `certsBody`): its key-set address otherwise always answers 200
 * (rule 15). Here the code exchange succeeds, so it is the key set that fails, not the token address.
 */
import { afterEach, describe, expect, it } from "vitest";

import { Secret } from "../../server/config.js";
import { createOidcFlow } from "../../server/oidc.js";
import { COOKIE_NAME } from "../../server/sessionPolicy.js";
import { LOGIN_COOKIE_NAME } from "../../server/loginState.js";
import { SESSION_KEY_PREFIX } from "../../server/sessionStore.js";
import { build } from "../support/build.js";
import { testClock } from "../support/clock.js";
import { startFakeKeycloak } from "../support/fakeKeycloak.js";
import type { FakeKeycloak } from "../support/fakeKeycloak.js";
import { everythingIn, request, setCookies } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

const CLIENT_ID = "osprey-pages";
const ORIGIN = "https://pages.test.example";
const REFUSED_WORDS = "Sign-in was refused. Nothing about your access has changed.";
const UNAVAILABLE_WORDS = "Sign-in is not available just now. Nothing about your access has changed.";

const fakes: FakeKeycloak[] = [];
afterEach(async () => {
  while (fakes.length) await fakes.pop()?.stop();
});

async function rig() {
  const clientSecret = generateSecret();
  const fake = await startFakeKeycloak({ clientId: CLIENT_ID, clientSecret, redirectUri: `${ORIGIN}/session/callback` });
  fakes.push(fake);
  const clock = testClock();
  const flow = createOidcFlow(
    { issuer: fake.issuer, clientId: CLIENT_ID, clientSecret: new Secret(clientSecret), publicOrigin: ORIGIN },
    { now: clock },
  );
  const built = build({ codeFlow: flow, clock });
  return { fake, app: built.app, store: built.store };
}

/** Start, sign in at the provider, come back: the exchange succeeds, then the key set is asked. */
async function comeBackWith(r: Awaited<ReturnType<typeof rig>>) {
  const started = await request(r.app).get("/session/sign-in");
  expect(started.status).toBe(302);
  const loginCookie = (setCookies(started).find((c) => c.startsWith(`${LOGIN_COOKIE_NAME}=`)) as string).split(";")[0] as string;
  const callback = new URL(r.fake.authorise(started.headers["location"] as string));
  return request(r.app).get(`${callback.pathname}${callback.search}`).set("Cookie", loginCookie);
}

function expectNoSession(r: Awaited<ReturnType<typeof rig>>, res: { headers: Record<string, unknown> }) {
  expect(setCookies(res as never).some((c) => c.startsWith(`${COOKIE_NAME}=`) && !/^[^=]+=;/.test(c))).toBe(false);
  expect(r.store.keys().filter((key) => key.startsWith(SESSION_KEY_PREFIX))).toEqual([]);
}

describe("the realm's key set failing after the code exchange (ADR-044)", () => {
  for (const status of [500, 502, 503]) {
    it(`a key set that answers ${status} is a 503, not a refusal`, async () => {
      const r = await rig();
      r.fake.certsStatus = status;
      const res = await comeBackWith(r);
      expect(r.fake.tokenCalls, "the code was exchanged, so it is the key set that failed").toBe(1);
      expect(r.fake.certsCalls).toBeGreaterThan(0);
      expect(res.status).toBe(503);
      expect(res.text).toContain(UNAVAILABLE_WORDS);
      expect(everythingIn(res)).not.toContain(REFUSED_WORDS);
      expectNoSession(r, res);
    });
  }

  it("an answer that is not a key set is a 503, not a refusal", async () => {
    const r = await rig();
    r.fake.certsBody = JSON.stringify({ keys: "not a list" });
    const res = await comeBackWith(r);
    expect(r.fake.tokenCalls).toBe(1);
    expect(res.status).toBe(503);
    expect(res.text).toContain(UNAVAILABLE_WORDS);
    expectNoSession(r, res);
  });

  it("an answer that is not JSON is a 503, not a refusal", async () => {
    const r = await rig();
    r.fake.certsBody = "<html>bad gateway</html>";
    const res = await comeBackWith(r);
    expect(res.status).toBe(503);
    expect(res.text).toContain(UNAVAILABLE_WORDS);
    expectNoSession(r, res);
  });

  it("a token signed by another key is still a refusal", async () => {
    const r = await rig();
    r.fake.signWithOtherKey = true;
    const res = await comeBackWith(r);
    expect(r.fake.certsCalls).toBeGreaterThan(0);
    expect(res.status).toBe(403);
    expect(res.text).toContain(REFUSED_WORDS);
    expectNoSession(r, res);
  });

  it("a key set that answers again after a failure lets the next sign-in through", async () => {
    const r = await rig();
    r.fake.certsStatus = 502;
    expect((await comeBackWith(r)).status).toBe(503);
    r.fake.certsStatus = undefined;
    const res = await comeBackWith(r);
    expect(res.status).toBe(302);
  });
});
