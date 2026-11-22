/**
 * A held release folder is removed when it expires, with nobody reading or writing (slice IS5a, round 7). The brief: the held
 * folder is "removed after import, on sign-out and at session expiry". The pages process holds it in its own memory, so a
 * folder that a person checks and abandons must leave that memory by itself, not wait for a later upload.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - an expired folder that stays in the process until something reads it or writes another key -> "removes an expired key with no read"
 *  - a sweep that removes what has not expired                                                      -> "keeps what has not expired"
 *  - a sweep timer that keeps the process alive, or that nothing stops                              -> "does not keep the process alive"
 *  - an app whose own held-folder store is not swept                                                -> "the app's own held-folder store"
 *
 * The earlier case (`studio-releases.test.ts` SR13) asserted removal through `keys()`, which itself removes what has expired as
 * it reads, so it could not fail for this fault. These cases count the store's entries with `size()`, which removes nothing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PAGES } from "../../server/pageList.js";
import { MemorySessionStore, STAGED_KEY_PREFIX } from "../../server/sessionStore.js";
import { STAGED_TTL_SECONDS, heldBy } from "../../server/staging.js";
import { newRecord, randomToken } from "../../server/sessionPolicy.js";
import { build } from "../support/build.js";
import { testClock } from "../support/clock.js";

const SWEEP_MS = 60_000;
const key = () => `${STAGED_KEY_PREFIX}${randomToken()}`;

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("the in-memory store's sweep", () => {
  it("removes an expired key with no read and no write: counted by an observation that removes nothing", async () => {
    const clock = testClock();
    const store = new MemorySessionStore({ clock, sweepEveryMs: SWEEP_MS });
    await store.set(key(), "x", 60);
    expect(store.size()).toBe(1);
    clock.advance(61);
    // Nothing has read the key, and nothing has written another: the entry is still held until the sweep runs.
    expect(store.size()).toBe(1);
    await vi.advanceTimersByTimeAsync(SWEEP_MS);
    expect(store.size()).toBe(0);
    store.close();
  });

  it("keeps what has not expired, and removes only what has", async () => {
    const clock = testClock();
    const store = new MemorySessionStore({ clock, sweepEveryMs: SWEEP_MS });
    const short = key();
    const long = key();
    await store.set(short, "short", 60);
    await store.set(long, "long", 3600);
    clock.advance(120);
    await vi.advanceTimersByTimeAsync(SWEEP_MS);
    expect(store.size()).toBe(1);
    expect(await store.get(long)).toBe("long");
    expect(await store.get(short)).toBeNull();
    store.close();
  });

  it("does not keep the process alive, and `close` stops it", async () => {
    const spy = vi.spyOn(globalThis, "setInterval");
    const store = new MemorySessionStore({ clock: testClock(), sweepEveryMs: SWEEP_MS });
    expect(spy).toHaveBeenCalledTimes(1);
    const timer = spy.mock.results[0]?.value as { hasRef(): boolean };
    expect(timer.hasRef()).toBe(false);
    expect(vi.getTimerCount()).toBe(1);
    store.close();
    expect(vi.getTimerCount()).toBe(0);
    spy.mockRestore();
  });

  it("has no timer unless asked for one (a test's store, a session's store)", () => {
    const store = new MemorySessionStore({ clock: testClock() });
    expect(vi.getTimerCount()).toBe(0);
    store.close();
  });

  it("a folder held for a session is gone from the process's memory half an hour after its last step, with nobody reading it", async () => {
    const clock = testClock();
    const store = new MemorySessionStore({ clock, sweepEveryMs: SWEEP_MS });
    const session = {
      auth: newRecord(
        { subject: "sub-a", displayName: "Alex", accessToken: "a", refreshToken: "r", idpSessionExpiresAt: clock() + 10 * 3600 * 1000 },
        clock(),
      ),
      staged: [] as string[],
    };
    const held = heldBy(store, session, clock);
    await held.put({ v: 1, subject: "sub-a", caseId: "c", datasetId: "d", files: { "release.yaml": "x" } });
    expect(store.size()).toBe(1);
    clock.advance(STAGED_TTL_SECONDS + 1);
    await vi.advanceTimersByTimeAsync(SWEEP_MS);
    expect(store.size()).toBe(0);
    store.close();
  });
});

describe("the app's own held-folder store", () => {
  it("is swept by its own timer, which does not keep the process alive", async () => {
    const spy = vi.spyOn(globalThis, "setInterval");
    // `stagedApart`: no store is handed to the app, so it makes its own, as it does in a deployment.
    const built = build({ pages: PAGES, stagedApart: true });
    const studio = built.app.locals["studio"] as { store: MemorySessionStore };
    expect(studio.store).toBeInstanceOf(MemorySessionStore);
    const timers = spy.mock.results.map((r) => r.value as { hasRef(): boolean });
    expect(timers.length).toBeGreaterThanOrEqual(1);
    expect(timers.every((t) => !t.hasRef())).toBe(true);
    await studio.store.set(key(), "x", 60);
    expect(studio.store.size()).toBe(1);
    built.clock.advance(61);
    await vi.advanceTimersByTimeAsync(SWEEP_MS);
    expect(studio.store.size()).toBe(0);
    spy.mockRestore();
  });
});
