/**
 * The `express-session` store over the key-value store (ADR-152 decision 2). Where the lifetimes are
 * enforced, so each is shown here by a write or a read the store must refuse, through the package's own
 * callback interface and the in-memory key-value store that refuses what Valkey refuses.
 */
import { describe, expect, it } from "vitest";
import type { SessionData } from "express-session";

import { PagesSessionStore } from "../../server/expressStore.js";
import { ABSOLUTE_SECONDS, IDLE_SECONDS } from "../../server/sessionPolicy.js";
import type { SessionRecord } from "../../server/sessionPolicy.js";
import { MemorySessionStore, SESSION_KEY_PREFIX } from "../../server/sessionStore.js";
import { testClock } from "../support/clock.js";

const SID = "S".repeat(43);
const KEY = `${SESSION_KEY_PREFIX}${SID}`;

function record(now: number, overrides: Partial<SessionRecord> = {}): SessionRecord {
  return {
    v: 1,
    subject: "sub",
    displayName: "Alex Example",
    accessToken: "a",
    refreshToken: "r",
    csrfToken: "c".repeat(43),
    createdAt: now,
    idpSessionExpiresAt: now + 10 * 3600 * 1000,
    ...overrides,
  };
}

function data(auth: SessionRecord | undefined): SessionData {
  return { cookie: {} as SessionData["cookie"], ...(auth ? { auth } : {}) };
}

type Callback = (error?: unknown, result?: unknown) => void;
const call = <T>(run: (cb: Callback) => void): Promise<T | undefined> =>
  new Promise((resolve, reject) => {
    run((error, result) => (error ? reject(error as Error) : resolve(result as T)));
  });

function setup() {
  const clock = testClock();
  const kv = new MemorySessionStore({ clock });
  const store = new PagesSessionStore(kv, clock);
  return { clock, kv, store };
}

describe("PagesSessionStore", () => {
  it("writes every key with a TTL: the idle hour at most, and what remains of the absolute and the provider's lifetime", async () => {
    const { clock, kv, store } = setup();
    await call((cb) => store.set(SID, data(record(clock())), cb));
    expect(kv.ttl(KEY)).toBe(IDLE_SECONDS);

    const short = `${SESSION_KEY_PREFIX}${"T".repeat(43)}`;
    await call((cb) => store.set("T".repeat(43), data(record(clock(), { idpSessionExpiresAt: clock() + 600_000 })), cb));
    expect(kv.ttl(short)).toBe(600);

    const old = `${SESSION_KEY_PREFIX}${"U".repeat(43)}`;
    await call((cb) => store.set("U".repeat(43), data(record(clock() - (ABSOLUTE_SECONDS - 120) * 1000)), cb));
    expect(kv.ttl(old)).toBe(120);
  });

  it("refuses to store a session that is not signed in, as it has no lifetime to carry", async () => {
    const { kv, store } = setup();
    await expect(call((cb) => store.set(SID, data(undefined), cb))).rejects.toThrow(/not signed in/);
    expect(kv.keys()).toEqual([]);
  });

  it("refuses an identifier it did not make, so no key is ever outside the prefix", async () => {
    const { clock, kv, store } = setup();
    for (const sid of ["short", "", `../${SID.slice(3)}`, "a".repeat(44)]) {
      await expect(call((cb) => store.set(sid, data(record(clock())), cb))).rejects.toThrow(/identifier/);
    }
    expect(await call((cb) => store.get("short", cb))).toBeNull();
    expect(kv.keys()).toEqual([]);
  });

  it("does not write a session whose lifetime is already spent, and deletes the key", async () => {
    const { clock, kv, store } = setup();
    await call((cb) => store.set(SID, data(record(clock())), cb));
    const spent = record(clock() - (ABSOLUTE_SECONDS + 1) * 1000);
    await call((cb) => store.set(SID, data(spent), cb));
    expect(kv.keys()).toEqual([]);
  });

  it("refuses, and deletes, a record past its absolute lifetime that the key-value store still holds", async () => {
    const { clock, kv, store } = setup();
    const spent = record(clock() - (ABSOLUTE_SECONDS + 1) * 1000);
    // Written straight into the key-value store with a TTL: its own expiry has not fired.
    await kv.set(KEY, JSON.stringify(data(spent)), 3600);
    expect(await call((cb) => store.get(SID, cb))).toBeNull();
    expect(kv.keys()).toEqual([]);
  });

  it("refuses, and deletes, a record that is not a session record", async () => {
    const { kv, store } = setup();
    for (const junk of ["not json", "{}", '{"auth":{"v":2}}', "null", "[]"]) {
      await kv.set(KEY, junk, 60);
      expect(await call((cb) => store.get(SID, cb)), junk).toBeNull();
      expect(kv.keys(), junk).toEqual([]);
    }
  });

  it("reads back what it wrote, and touch slides the key but never past the absolute lifetime", async () => {
    const { clock, kv, store } = setup();
    const written = data(record(clock()));
    await call((cb) => store.set(SID, written, cb));
    expect(await call((cb) => store.get(SID, cb))).toMatchObject({ auth: { displayName: "Alex Example" } });

    clock.advance(IDLE_SECONDS - 10);
    await call((cb) => store.touch(SID, written, cb));
    expect(kv.ttl(KEY)).toBe(IDLE_SECONDS);

    // Active every half hour until 100 seconds short of the eight hours: the key may not outlast them.
    while (clock() < written.auth!.createdAt + (ABSOLUTE_SECONDS - 100) * 1000) {
      clock.advance(Math.min(1800, (written.auth!.createdAt + (ABSOLUTE_SECONDS - 100) * 1000 - clock()) / 1000));
      await call((cb) => store.touch(SID, written, cb));
    }
    expect(kv.ttl(KEY)).toBe(100);
  });

  it("touch on a key that has gone is not an error, and touch past the lifetime deletes", async () => {
    const { clock, kv, store } = setup();
    const written = data(record(clock()));
    await call((cb) => store.touch(SID, written, cb)); // nothing there
    await call((cb) => store.set(SID, written, cb));
    clock.advance(ABSOLUTE_SECONDS + 1);
    await call((cb) => store.touch(SID, written, cb));
    expect(kv.keys()).toEqual([]);
  });

  it("destroys, and destroying nothing is not an error", async () => {
    const { clock, kv, store } = setup();
    await call((cb) => store.set(SID, data(record(clock())), cb));
    await call((cb) => store.destroy(SID, cb));
    expect(kv.keys()).toEqual([]);
    await call((cb) => store.destroy(SID, cb));
  });
});
