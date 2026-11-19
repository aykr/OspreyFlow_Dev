/**
 * The startup path: `main` in `server/start.ts`, the function `main.ts` calls. The service refuses to start,
 * in words, when `OSPREY_PAGES_SESSION_SECRET` is missing, empty or shorter than 32 characters; the
 * words name the setting and the rule and never include the value; and with 32 characters it starts.
 */
import { afterEach, describe, expect, it } from "vitest";

import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { captureOutput } from "../support/capture.js";
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

  it.each([1, 8, 21, 31])("never includes a %i-character value, in the refusal or in anything written", async (length) => {
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
