/**
 * The startup path: `main` in `server/start.ts`, the function `main.ts` calls. The service refuses to start,
 * in words, when `OSPREY_PAGES_SESSION_SECRET` is missing, empty or shorter than 32 characters; the
 * words name the setting and the rule and never include the value; and with 32 characters it starts.
 */
import { request as httpRequest } from "node:http";

import { afterEach, describe, expect, it } from "vitest";

import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { captureOutput } from "../support/capture.js";
import { startFakeKeycloak } from "../support/fakeKeycloak.js";
import { request } from "../support/http.js";
import { CLIENT_ID, ORIGIN, REDIRECT_URI, signInAs } from "../support/providerRig.js";
import { generateSecret } from "../support/secret.js";

const NAME = "OSPREY_PAGES_SESSION_SECRET";

function channel() {
  const logs: string[] = [];
  const errors: string[] = [];
  const exits: number[] = [];
  return {
    logs,
    errors,
    exits,
    log: (m: string) => void logs.push(m),
    error: (m: string) => void errors.push(m),
    exit: (c: number) => void exits.push(c),
  };
}

const running: Running[] = [];
afterEach(async () => {
  while (running.length) await running.pop()?.stop();
});

/** Starts the service as `main.ts` does, but with the in-memory store and a free loopback port. */
async function startWith(env: NodeJS.ProcessEnv) {
  const captured = captureOutput();
  const io = channel();
  let result: Running | undefined;
  try {
    result = await main({ OSPREY_PAGES_PORT: "0", ...env }, io, { store: new MemorySessionStore(), host: "127.0.0.1" });
  } finally {
    captured.restore();
  }
  if (result) running.push(result);
  return { result, channel: io, output: captured.text() };
}

describe("main refuses to start without a usable secret, in words", () => {
  const refused: Array<[string, NodeJS.ProcessEnv]> = [
    ["missing", {}],
    ["empty", { [NAME]: "" }],
    ["31 characters", { [NAME]: generateSecret(31) }],
  ];

  it.each(refused)("%s: no service, exit 1, the setting and the rule named", async (_name, env) => {
    const { result, channel } = await startWith(env);
    expect(result).toBeUndefined();
    expect(channel.exits).toEqual([1]);
    expect(channel.logs.join("\n")).not.toMatch(/listening/);
    const said = channel.errors.join("\n");
    expect(said).toContain(NAME);
    expect(said).toMatch(/at least 32 characters|is required/);
  });

  it("names the rule for each: required when missing or empty, at least 32 when short", async () => {
    expect((await startWith({})).channel.errors.join("\n")).toMatch(/required/);
    expect((await startWith({ [NAME]: "" })).channel.errors.join("\n")).toMatch(/required/);
    expect((await startWith({ [NAME]: generateSecret(31) })).channel.errors.join("\n")).toMatch(/at least 32 characters/);
  });

  it.each([8, 21, 31])("never includes a %i-character value, in the refusal or in anything written", async (length) => {
    const given = generateSecret(length);
    const { result, channel, output } = await startWith({ [NAME]: given });
    expect(result).toBeUndefined();
    expect(channel.errors.join("\n")).not.toBe("");
    for (const text of [...channel.errors, ...channel.logs, output]) {
      expect(text).not.toContain(given);
      expect(text).not.toContain(given.slice(0, 6));
    }
  });

  it("does not echo a short value when something else is also wrong", async () => {
    const given = generateSecret(10);
    const { channel, output } = await startWith({ [NAME]: given, OSPREY_PAGES_VALKEY_DB: "99" });
    expect(channel.exits).toEqual([1]);
    for (const text of [...channel.errors, output]) expect(text).not.toContain(given);
  });
});

describe("main starts with 32 characters", () => {
  it("listens, answers its health route, and says so without the value", async () => {
    const given = generateSecret(32);
    const { result, channel, output } = await startWith({ [NAME]: given });
    expect(result).toBeDefined();
    expect(channel.exits).toEqual([]);
    expect(channel.logs.join("\n")).toMatch(/listening on/);

    const res = await fetch(`http://127.0.0.1:${result?.port}/healthz`);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: "ok" });

    for (const text of [...channel.errors, ...channel.logs, output, ...[...res.headers.values()]]) {
      expect(text).not.toContain(given);
    }
  });

  it("serves the page: a visitor with no session is sent to sign in", async () => {
    const { result } = await startWith({ [NAME]: generateSecret(32) });
    const res = await fetch(`http://127.0.0.1:${result?.port}/`, { redirect: "manual" });
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("/session/sign-in");
  });
});

/**
 * Round 3 of PL9b: the realm client registers `http://pages:8090/session/back-channel-logout` (`harness/realm.py`,
 * `pages_backchannel_logout_url`), and Keycloak posts there from its own container, on the internal network: plain HTTP, no
 * proxy in front (so no `X-Forwarded-Proto`), the Host the compose service name and port. The service's real listener, started
 * as `main.ts` starts it, must answer that call: a genuine logout token ends the session it names, and anything else is refused
 * in plain words with nothing ended. (The listener binds every interface: `start.ts` listens on `0.0.0.0` unless a test says
 * otherwise, which is what the address needs.)
 */
describe("the back-channel logout address on the service's own listener", () => {
  const PATH = "/session/back-channel-logout";

  /** The call as Keycloak makes it: a bare form POST to the service's own address, with that address in `Host`. */
  function fromKeycloak(port: number, body: string, contentType = "application/x-www-form-urlencoded"): Promise<{ status: number; type: string; text: string; headers: string[] }> {
    return new Promise((resolve, reject) => {
      const call = httpRequest(
        { host: "127.0.0.1", port, path: PATH, method: "POST", headers: { host: "pages:8090", "content-type": contentType, "content-length": Buffer.byteLength(body) } },
        (res) => {
          const chunks: Buffer[] = [];
          res.on("data", (chunk: Buffer) => chunks.push(chunk));
          res.on("end", () =>
            resolve({ status: res.statusCode ?? 0, type: String(res.headers["content-type"] ?? ""), text: Buffer.concat(chunks).toString("utf8"), headers: Object.keys(res.headers) }),
          );
        },
      );
      call.on("error", reject);
      call.end(body);
    });
  }

  async function started() {
    const clientSecret = generateSecret();
    const fake = await startFakeKeycloak({ clientId: CLIENT_ID, clientSecret, redirectUri: REDIRECT_URI });
    const captured = captureOutput();
    let result: Running | undefined;
    try {
      result = await main(
        {
          OSPREY_PAGES_PORT: "0",
          OSPREY_PAGES_SESSION_SECRET: generateSecret(32),
          OSPREY_PAGES_OIDC_ISSUER: fake.issuer,
          OSPREY_PAGES_CLIENT_ID: CLIENT_ID,
          OSPREY_PAGES_CLIENT_SECRET: clientSecret,
          OSPREY_PAGES_PUBLIC_ORIGIN: ORIGIN,
        },
        { log: () => undefined, error: () => undefined, exit: () => undefined },
        { store: new MemorySessionStore(), host: "0.0.0.0" },
      );
    } finally {
      captured.restore();
    }
    if (!result) throw new Error("the service did not start");
    running.push(result);
    return { fake, port: result.port, base: `http://127.0.0.1:${result.port}`, stop: () => fake.stop() };
  }

  it("ends the session a genuine token names, from a call shaped as Keycloak's is", async () => {
    const { fake, port, base, stop } = await started();
    try {
      const person = await signInAs({ fake, app: base });
      const before = await request(base).get("/").set("Cookie", person.cookie);
      expect(before.status, "the person is signed in").toBe(200);

      const answer = await fromKeycloak(port, new URLSearchParams({ logout_token: await fake.logoutToken(person.sid) }).toString());
      expect(answer.status).toBe(200);
      expect(answer.text).toBe("");

      const after = await request(base).get("/").set("Cookie", person.cookie);
      expect(after.status, "the pages session ended").toBe(302);
      expect(after.headers["location"]).toBe("/session/sign-in");
    } finally {
      await stop();
    }
  });

  it("refuses an unsigned, a badly signed and a missing token in plain words, and ends nothing", async () => {
    const { fake, port, base, stop } = await started();
    try {
      const person = await signInAs({ fake, app: base });
      const bodies = [
        new URLSearchParams({ logout_token: await fake.logoutToken(person.sid, { signedWith: "none" }) }).toString(),
        new URLSearchParams({ logout_token: await fake.logoutToken(person.sid, { signedWith: "other" }) }).toString(),
        new URLSearchParams({ logout_token: "not-a-token" }).toString(),
        "",
      ];
      for (const body of bodies) {
        const answer = await fromKeycloak(port, body);
        expect({ status: answer.status, text: answer.text }).toEqual({ status: 400, text: "Refused" });
        expect(answer.type).toMatch(/^text\/plain/);
        expect(answer.headers).not.toContain("set-cookie");
      }
      expect((await request(base).get("/").set("Cookie", person.cookie)).status, "nothing ended").toBe(200);
    } finally {
      await stop();
    }
  });
});
