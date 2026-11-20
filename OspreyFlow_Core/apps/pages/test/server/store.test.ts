/**
 * The session store has one interface and two implementations. The in-memory one must refuse what
 * Valkey refuses (rule 15: a fixture standing in for a dependency models its refusals, not only its
 * grants): a write with no TTL (the deployment's Valkey runs `noeviction`, so a key with no limit is a
 * leak), a key outside the service's prefix, a value over the limit.
 */
import { describe, expect, it } from "vitest";

import {
  LOGIN_KEY_PREFIX,
  MAX_VALUE_BYTES,
  MemorySessionStore,
  SESSION_KEY_PREFIX,
  StoreRefusal,
  ValkeySessionStore,
} from "../../server/sessionStore.js";
import type { ValkeyClient } from "../../server/sessionStore.js";
import { testClock } from "../support/clock.js";

const KEY = `${SESSION_KEY_PREFIX}abc`;

describe("the in-memory store refuses what Valkey refuses", () => {
  it.each([
    ["no TTL", undefined],
    ["a zero TTL", 0],
    ["a negative TTL", -5],
    ["a TTL that is not a number", Number.NaN],
    ["a TTL that is not whole seconds", 1.5],
    ["an unlimited TTL", Number.POSITIVE_INFINITY],
  ])("a write with %s", async (_name, ttl) => {
    const store = new MemorySessionStore({ clock: testClock() });
    await expect(store.set(KEY, "v", ttl as number)).rejects.toThrow(StoreRefusal);
    await expect(store.set(KEY, "v", ttl as number)).rejects.toThrow(/TTL/);
    expect(store.keys()).toEqual([]);
  });

  it.each([
    ["a key with no prefix", "abc"],
    ["another service's prefix", "conduit-session:abc"],
    ["the prefix alone", SESSION_KEY_PREFIX],
    ["the prefix in the middle", `x${SESSION_KEY_PREFIX}abc`],
  ])("a write to %s", async (_name, key) => {
    const store = new MemorySessionStore({ clock: testClock() });
    await expect(store.set(key, "v", 60)).rejects.toThrow(/prefix/);
    expect(store.keys()).toEqual([]);
  });

  it("a value over the limit, counted in bytes, and not at it", async () => {
    const store = new MemorySessionStore({ clock: testClock() });
    await expect(store.set(KEY, "x".repeat(MAX_VALUE_BYTES + 1), 60)).rejects.toThrow(/limit/);
    await expect(store.set(KEY, "é".repeat(MAX_VALUE_BYTES / 2 + 1), 60)).rejects.toThrow(/limit/); // two bytes each
    expect(store.keys()).toEqual([]);
    await store.set(KEY, "x".repeat(MAX_VALUE_BYTES), 60);
    expect(store.keys()).toEqual([KEY]);
  });

  it("and a refused write leaves an existing key as it was, value and TTL", async () => {
    const clock = testClock();
    const store = new MemorySessionStore({ clock });
    await store.set(KEY, "first", 60);
    await expect(store.set(KEY, "second", undefined as unknown as number)).rejects.toThrow(StoreRefusal);
    expect(await store.get(KEY)).toBe("first");
    expect(store.ttl(KEY)).toBe(60);
  });

  it("a renewal with no TTL, and any read or delete outside the prefix", async () => {
    const store = new MemorySessionStore({ clock: testClock() });
    await store.set(KEY, "v", 60);
    await expect(store.expire(KEY, 0)).rejects.toThrow(StoreRefusal);
    await expect(store.get("abc")).rejects.toThrow(/prefix/);
    await expect(store.del("abc")).rejects.toThrow(/prefix/);
    await expect(store.expire("abc", 60)).rejects.toThrow(/prefix/);
  });
});

describe("the in-memory store, as Valkey behaves when it is allowed", () => {
  it("holds a value for its TTL and not a second longer", async () => {
    const clock = testClock();
    const store = new MemorySessionStore({ clock });
    await store.set(KEY, "v", 10);
    clock.advance(9);
    expect(await store.get(KEY)).toBe("v");
    expect(store.ttl(KEY)).toBe(1);
    clock.advance(1);
    expect(await store.get(KEY)).toBeNull();
    expect(store.keys()).toEqual([]);
    expect(store.ttl(KEY)).toBeNull();
  });

  it("renews, and says whether there was anything to renew", async () => {
    const clock = testClock();
    const store = new MemorySessionStore({ clock });
    await store.set(KEY, "v", 10);
    clock.advance(5);
    expect(await store.expire(KEY, 10)).toBe(true);
    expect(store.ttl(KEY)).toBe(10);
    expect(await store.expire(`${SESSION_KEY_PREFIX}none`, 10)).toBe(false);
    clock.advance(11);
    expect(await store.expire(KEY, 10)).toBe(false); // already expired
  });

  it("deletes", async () => {
    const store = new MemorySessionStore({ clock: testClock() });
    await store.set(KEY, "v", 10);
    await store.del(KEY);
    expect(await store.get(KEY)).toBeNull();
    await store.del(KEY); // deleting nothing is not an error
  });
});

/** A client that records each call and models Valkey's own refusal of a bad `EX`. */
function recordingClient(): ValkeyClient & { calls: unknown[][]; data: Map<string, string> } {
  const calls: unknown[][] = [];
  const data = new Map<string, string>();
  return {
    calls,
    data,
    async set(key, value, mode, seconds) {
      calls.push(["set", key, value, mode, seconds]);
      if (mode !== "EX" || !Number.isInteger(seconds) || seconds <= 0) {
        throw new Error("ERR invalid expire time in 'set' command");
      }
      data.set(key, value);
      return "OK";
    },
    async get(key) {
      calls.push(["get", key]);
      return data.get(key) ?? null;
    },
    async expire(key, seconds) {
      calls.push(["expire", key, seconds]);
      return data.has(key) ? 1 : 0;
    },
    async del(...keys) {
      calls.push(["del", ...keys]);
      let n = 0;
      for (const k of keys) if (data.delete(k)) n++;
      return n;
    },
    async getdel(key) {
      calls.push(["getdel", key]);
      const value = data.get(key) ?? null;
      data.delete(key);
      return value;
    },
  };
}

describe("the login records (a started sign-in, PL9a)", () => {
  const LOGIN_KEY = `${LOGIN_KEY_PREFIX}abc`;

  it("are under their own prefix, with the same rules: a TTL, a limit, no other prefix", async () => {
    const store = new MemorySessionStore({ clock: testClock() });
    await store.set(LOGIN_KEY, "v", 600);
    expect(store.keys()).toEqual([LOGIN_KEY]);
    await expect(store.set(LOGIN_KEY, "v", 0)).rejects.toThrow(StoreRefusal);
    await expect(store.set(LOGIN_KEY_PREFIX, "v", 60)).rejects.toThrow(/prefix/);
    await expect(store.set(`x${LOGIN_KEY}`, "v", 60)).rejects.toThrow(/prefix/);
  });

  it("are read once: `take` gives the value to one caller and removes it, in the memory store and the Valkey one", async () => {
    const memory = new MemorySessionStore({ clock: testClock() });
    await memory.set(LOGIN_KEY, "once", 600);
    expect(await Promise.all([memory.take(LOGIN_KEY), memory.take(LOGIN_KEY)])).toEqual(["once", null]);
    expect(memory.keys()).toEqual([]);

    const client = recordingClient();
    const valkey = new ValkeySessionStore(client);
    await valkey.set(LOGIN_KEY, "once", 600);
    expect(await valkey.take(LOGIN_KEY)).toBe("once");
    expect(await valkey.take(LOGIN_KEY)).toBeNull();
    expect(client.calls.filter(([name]) => name === "getdel")).toHaveLength(2);
    await expect(valkey.take("abc")).rejects.toThrow(StoreRefusal);
  });

  it("an expired record is not taken", async () => {
    const clock = testClock();
    const store = new MemorySessionStore({ clock });
    await store.set(LOGIN_KEY, "v", 600);
    clock.advance(601);
    expect(await store.take(LOGIN_KEY)).toBeNull();
  });
});

describe("the Valkey store", () => {
  it("writes with SET … EX, the TTL in the same command so no key is ever without one", async () => {
    const client = recordingClient();
    const store = new ValkeySessionStore(client);
    await store.set(KEY, "v", 3600);
    expect(client.calls).toEqual([["set", KEY, "v", "EX", 3600]]);
    expect(await store.get(KEY)).toBe("v");
    expect(await store.expire(KEY, 100)).toBe(true);
    expect(await store.expire(`${SESSION_KEY_PREFIX}none`, 100)).toBe(false);
    await store.del(KEY);
    expect(await store.get(KEY)).toBeNull();
  });

  it("refuses, before it reaches the client, every write the in-memory store refuses", async () => {
    const client = recordingClient();
    const store = new ValkeySessionStore(client);
    await expect(store.set(KEY, "v", undefined as unknown as number)).rejects.toThrow(StoreRefusal);
    await expect(store.set(KEY, "v", 0)).rejects.toThrow(StoreRefusal);
    await expect(store.set("abc", "v", 60)).rejects.toThrow(StoreRefusal);
    await expect(store.set(KEY, "x".repeat(MAX_VALUE_BYTES + 1), 60)).rejects.toThrow(StoreRefusal);
    await expect(store.expire(KEY, -1)).rejects.toThrow(StoreRefusal);
    await expect(store.get("abc")).rejects.toThrow(StoreRefusal);
    await expect(store.del("abc")).rejects.toThrow(StoreRefusal);
    expect(client.calls).toEqual([]);
  });
});
