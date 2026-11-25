/**
 * The session store has one interface and two implementations. The in-memory one must refuse what
 * Valkey refuses (rule 15: a fixture standing in for a dependency models its refusals, not only its
 * grants): a write with no TTL (the deployment's Valkey runs `noeviction`, so a key with no limit is a
 * leak), a key outside the service's prefix, a value over the limit.
 */
import { describe, expect, it } from "vitest";

import {
  LOGIN_KEY_PREFIX,
  LOGOUT_JTI_PREFIX,
  MAX_VALUE_BYTES,
  MemorySessionStore,
  SESSION_KEY_PREFIX,
  STAGED_KEY_PREFIX,
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

/** What Valkey's `SCAN ... MATCH` glob means, as far as this service's keys need: `*`, `?`, `[...]` and a backslash escape. */
function globToRegExp(glob: string): RegExp {
  let out = "";
  for (let i = 0; i < glob.length; i += 1) {
    const c = glob.charAt(i);
    if (c === "*") out += "[\\s\\S]*";
    else if (c === "?") out += "[\\s\\S]";
    else if (c === "[") {
      const close = glob.indexOf("]", i + 1);
      if (close < 0) out += "\\[";
      else {
        out += `[${glob.slice(i + 1, close).replace(/\\/g, "\\\\")}]`;
        i = close;
      }
    } else if (c === "\\" && i + 1 < glob.length) {
      i += 1;
      out += glob.charAt(i).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    } else out += c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${out}$`);
}

/**
 * A client that records each call and models Valkey's own refusals, not only its grants (rule 15):
 *  - `SET` needs `EX` and a whole, positive number of seconds; with `NX` it answers null, and writes nothing, when the key holds
 *    a value; any other fifth word is a syntax error;
 *  - a key expires when its `EX` seconds are over (the clock moves by hand), and an expired key is not read, not renewed, not
 *    scanned;
 *  - `SCAN` takes a cursor it gave (or "0"), a `MATCH` glob and a `COUNT` hint, and returns a page of the matching live keys and
 *    the next cursor, "0" at the end. A page is at most `pageSize` keys (the real one may return fewer or none with a cursor that
 *    is not "0", and so does this one: a page of keys that do not match comes back empty and the scan goes on), so a scan that
 *    stops at its first page misses keys. A cursor it did not give is an error.
 */
function recordingClient(
  options: { clock?: () => number; pageSize?: number; withScan?: boolean } = {},
): ValkeyClient & { calls: unknown[][]; data: Map<string, string> } {
  const clock = options.clock ?? testClock();
  const pageSize = options.pageSize ?? 2;
  const calls: unknown[][] = [];
  const data = new Map<string, string>();
  const expiresAt = new Map<string, number>();
  const live = (key: string): boolean => {
    if (!data.has(key)) return false;
    const end = expiresAt.get(key);
    if (end !== undefined && end <= clock()) {
      data.delete(key);
      expiresAt.delete(key);
      return false;
    }
    return true;
  };
  const client: ValkeyClient & { calls: unknown[][]; data: Map<string, string> } = {
    calls,
    data,
    async set(key: string, value: string, mode: "EX", seconds: number, flag?: "NX") {
      calls.push(flag === undefined ? ["set", key, value, mode, seconds] : ["set", key, value, mode, seconds, flag]);
      if (mode !== "EX" || !Number.isInteger(seconds) || seconds <= 0) {
        throw new Error("ERR invalid expire time in 'set' command");
      }
      if (flag !== undefined && flag !== "NX") throw new Error("ERR syntax error");
      if (flag === "NX" && live(key)) return null;
      data.set(key, value);
      expiresAt.set(key, clock() + seconds * 1000);
      return "OK";
    },
    async get(key) {
      calls.push(["get", key]);
      return live(key) ? (data.get(key) ?? null) : null;
    },
    async expire(key, seconds) {
      calls.push(["expire", key, seconds]);
      if (!live(key)) return 0;
      expiresAt.set(key, clock() + seconds * 1000);
      return 1;
    },
    async del(...keys) {
      calls.push(["del", ...keys]);
      let n = 0;
      for (const k of keys) if (live(k) && data.delete(k)) n++;
      return n;
    },
    async getdel(key) {
      calls.push(["getdel", key]);
      const value = live(key) ? (data.get(key) ?? null) : null;
      data.delete(key);
      return value;
    },
  };
  if (options.withScan !== false) {
    // The cursor is the index of the next key in the order the keys were written, as a decimal string.
    client.scan = async (cursor, mode, pattern, countWord, count) => {
      calls.push(["scan", cursor, mode, pattern, countWord, count]);
      if (mode !== "MATCH" || countWord !== "COUNT" || !Number.isInteger(count) || count < 1) throw new Error("ERR syntax error");
      if (!/^(0|[1-9][0-9]*)$/.test(cursor)) throw new Error("ERR invalid cursor");
      const all = [...data.keys()].filter(live);
      const from = Number(cursor);
      if (from > all.length) throw new Error("ERR invalid cursor");
      const to = Math.min(from + Math.min(pageSize, count), all.length);
      const matcher = globToRegExp(pattern);
      return [to >= all.length ? "0" : String(to), all.slice(from, to).filter((key) => matcher.test(key))];
    };
  }
  return client;
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

describe("the Valkey store's claim and listKeys (the back-channel logout's replay refusal and its search)", () => {
  const JTI = `${LOGOUT_JTI_PREFIX}one`;

  it("the double refuses what Valkey refuses: NX on a key that holds a value, an EX that is over, a cursor it did not give", async () => {
    const clock = testClock();
    const client = recordingClient({ clock });
    expect(await client.set(KEY, "first", "EX", 10, "NX")).toBe("OK");
    expect(await client.set(KEY, "second", "EX", 10, "NX")).toBeNull();
    expect(await client.get(KEY)).toBe("first");
    clock.advance(10);
    expect(await client.get(KEY)).toBeNull();
    expect(await client.set(KEY, "third", "EX", 10, "NX")).toBe("OK");
    await expect(client.scan?.("17", "MATCH", "*", "COUNT", 10)).rejects.toThrow(/cursor/);
    await expect(client.scan?.("not-a-cursor", "MATCH", "*", "COUNT", 10)).rejects.toThrow(/cursor/);
  });

  it("claim: the first of one key wins, the second is refused and the first's value stays", async () => {
    const client = recordingClient();
    const store = new ValkeySessionStore(client);
    expect(await store.claim(JTI, "first", 60)).toBe(true);
    expect(await store.claim(JTI, "second", 60)).toBe(false);
    expect(client.data.get(JTI)).toBe("first");
    // The command is the one command: value, expiry and the condition together, so that no key is claimed without a limit.
    expect(client.calls).toEqual([
      ["set", JTI, "first", "EX", 60, "NX"],
      ["set", JTI, "second", "EX", 60, "NX"],
    ]);
  });

  it("claim: two at once, one wins", async () => {
    const store = new ValkeySessionStore(recordingClient());
    const results = await Promise.all([store.claim(JTI, "a", 60), store.claim(JTI, "b", 60), store.claim(JTI, "c", 60)]);
    expect(results.filter(Boolean)).toHaveLength(1);
  });

  it("claim: after the key's time is over it is accepted again, and then refused again", async () => {
    const clock = testClock();
    const store = new ValkeySessionStore(recordingClient({ clock }));
    expect(await store.claim(JTI, "v", 60)).toBe(true);
    clock.advance(59);
    expect(await store.claim(JTI, "v", 60)).toBe(false);
    clock.advance(1);
    expect(await store.claim(JTI, "v", 60)).toBe(true);
    expect(await store.claim(JTI, "v", 60)).toBe(false);
  });

  it("claim: refuses, before it reaches the client, what the other writes refuse, and a staged key", async () => {
    const client = recordingClient();
    const store = new ValkeySessionStore(client);
    await expect(store.claim(JTI, "v", 0)).rejects.toThrow(StoreRefusal);
    await expect(store.claim(JTI, "v", undefined as unknown as number)).rejects.toThrow(StoreRefusal);
    await expect(store.claim("one", "v", 60)).rejects.toThrow(StoreRefusal);
    await expect(store.claim(`${STAGED_KEY_PREFIX}one`, "v", 60)).rejects.toThrow(StoreRefusal);
    expect(client.calls).toEqual([]);
  });

  it("listKeys: exactly the keys under the prefix, across every cursor, as they were written", async () => {
    const client = recordingClient({ pageSize: 2 });
    const store = new ValkeySessionStore(client);
    const mine = ["a", "b", "c", "d", "e", "f", "g"].map((name) => `${SESSION_KEY_PREFIX}${name}`);
    for (const key of mine) await store.set(key, "v", 60);
    // Keys of other prefixes sit between them in the scan's order, and one that only looks like the prefix.
    await store.set(`${LOGIN_KEY_PREFIX}x`, "v", 60);
    await store.set(`${LOGOUT_JTI_PREFIX}y`, "v", 60);
    await store.set(`${SESSION_KEY_PREFIX}h`, "v", 60);
    await client.set("pages-session-not-quite", "v", "EX", 60);
    await client.set(`x${SESSION_KEY_PREFIX}z`, "v", "EX", 60);

    const found = await store.listKeys(SESSION_KEY_PREFIX);
    expect([...found].sort()).toEqual([...mine, `${SESSION_KEY_PREFIX}h`].sort());
    expect(new Set(found).size).toBe(found.length);
    const scans = client.calls.filter(([name]) => name === "scan");
    expect(scans.length).toBeGreaterThan(3); // more than one page: a scan that stopped at the first would miss keys
    expect(scans[0]).toEqual(["scan", "0", "MATCH", `${SESSION_KEY_PREFIX}*`, "COUNT", 200]);
    expect(scans.at(-1)?.[1]).not.toBe("0");
  });

  it("listKeys: a key that has expired is not listed, and a prefix with nothing under it gives none", async () => {
    const clock = testClock();
    const store = new ValkeySessionStore(recordingClient({ clock }));
    await store.set(`${SESSION_KEY_PREFIX}old`, "v", 10);
    clock.advance(5);
    await store.set(`${SESSION_KEY_PREFIX}new`, "v", 60);
    clock.advance(6);
    expect(await store.listKeys(SESSION_KEY_PREFIX)).toEqual([`${SESSION_KEY_PREFIX}new`]);
    expect(await store.listKeys(LOGIN_KEY_PREFIX)).toEqual([]);
  });

  it("listKeys: a prefix holds no glob character that matches more than it says", async () => {
    const client = recordingClient();
    const store = new ValkeySessionStore(client);
    await store.set(`${SESSION_KEY_PREFIX}a`, "v", 60);
    // The pattern sent is the prefix and one star: no other character of the prefix is a glob.
    await store.listKeys(SESSION_KEY_PREFIX);
    const pattern = client.calls.find(([name]) => name === "scan")?.[3];
    expect(pattern).toBe(`${SESSION_KEY_PREFIX}*`);
    expect(String(pattern).replace(/\*$/, "")).not.toMatch(/[*?[\]\\]/);
  });

  it("listKeys: refuses a prefix that is not ours, a staged one, and a client that cannot scan", async () => {
    const store = new ValkeySessionStore(recordingClient());
    await expect(store.listKeys("other:")).rejects.toThrow(StoreRefusal);
    await expect(store.listKeys(STAGED_KEY_PREFIX)).rejects.toThrow(StoreRefusal);
    await expect(new ValkeySessionStore(recordingClient({ withScan: false })).listKeys(SESSION_KEY_PREFIX)).rejects.toThrow(/scan/);
  });

  it("listKeys and claim agree with the in-memory store on the same steps", async () => {
    const clock = testClock();
    const memory = new MemorySessionStore({ clock });
    const valkey = new ValkeySessionStore(recordingClient({ clock }));
    for (const store of [memory, valkey]) {
      await store.set(`${SESSION_KEY_PREFIX}a`, "v", 60);
      await store.set(`${SESSION_KEY_PREFIX}b`, "v", 60);
      await store.set(`${LOGIN_KEY_PREFIX}c`, "v", 60);
    }
    expect([...(await valkey.listKeys(SESSION_KEY_PREFIX))].sort()).toEqual([...(await memory.listKeys(SESSION_KEY_PREFIX))].sort());
    expect(await valkey.claim(JTI, "v", 5)).toBe(await memory.claim(JTI, "v", 5));
    expect(await valkey.claim(JTI, "v", 5)).toBe(await memory.claim(JTI, "v", 5));
    clock.advance(5);
    expect(await valkey.claim(JTI, "v", 5)).toBe(await memory.claim(JTI, "v", 5));
  });
});
