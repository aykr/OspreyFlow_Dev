/**
 * The held release folder and the upload page's registration (slice IS5a): the store's rules for the new prefix, the folder's
 * ownership and lifetime, and the refusal of an upload page that cannot take a POST. The route-level cases (a token that is
 * another session's, the cap in words, removal after the import and on sign-out) are `test/default/studio-releases.test.ts`'s;
 * these are the units under them, each with a planted fault that shows its check can fail (rule 15).
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a staged value over the folder's cap, or a session value allowed the staged cap -> "the store's value limit"
 *  - a folder read by a session that did not stage it, or for another person        -> "ownership"
 *  - a folder that outlives the session or the half hour                            -> "lifetime"
 *  - an upload page that cannot take a POST                                         -> "an upload page"
 */
import { describe, expect, it } from "vitest";

import { registerPages } from "../../server/pages.js";
import type { PageModule } from "../../server/pages.js";
import { newRecord, randomToken } from "../../server/sessionPolicy.js";
import { MAX_STAGED_VALUE_BYTES, MAX_VALUE_BYTES, MemorySessionStore, SESSION_KEY_PREFIX, STAGED_KEY_PREFIX, StoreRefusal } from "../../server/sessionStore.js";
import { MAX_HELD, STAGED_TTL_SECONDS, StagedTooLarge, endStaged, heldBy } from "../../server/staging.js";
import type { Staged } from "../../server/staging.js";
import { testClock } from "../support/clock.js";

const provided = (subject = "sub-a") => ({
  subject,
  displayName: "Alex",
  accessToken: "a",
  refreshToken: "r",
  idpSessionExpiresAt: Date.UTC(2026, 10, 19, 9, 0, 0) + 10 * 3600 * 1000,
});

function folder(subject = "sub-a", files: Record<string, string> = { "release.yaml": "x" }): Staged {
  return { v: 1, subject, caseId: "c", datasetId: "d", files };
}

function setup(subject = "sub-a") {
  const clock = testClock();
  const store = new MemorySessionStore({ clock });
  const session: { auth: ReturnType<typeof newRecord>; staged?: string[] } = { auth: newRecord(provided(subject), clock()) };
  return { clock, store, session, held: heldBy(store, session, clock) };
}

describe("the store's value limit", () => {
  it("allows a staged folder what a session may not hold, and still refuses a session value over its own limit", async () => {
    const store = new MemorySessionStore();
    const big = "x".repeat(MAX_VALUE_BYTES + 1);
    await store.set(`${STAGED_KEY_PREFIX}${randomToken()}`, big, 60);
    await expect(store.set(`${SESSION_KEY_PREFIX}${randomToken()}`, big, 60)).rejects.toBeInstanceOf(StoreRefusal);
  });

  it("refuses a staged value over its own limit, and a staged key with no time limit", async () => {
    const store = new MemorySessionStore();
    await expect(store.set(`${STAGED_KEY_PREFIX}${randomToken()}`, "x".repeat(MAX_STAGED_VALUE_BYTES + 1), 60)).rejects.toBeInstanceOf(StoreRefusal);
    await expect(store.set(`${STAGED_KEY_PREFIX}${randomToken()}`, "x", 0)).rejects.toBeInstanceOf(StoreRefusal);
    await expect(store.set("pages-other:abc", "x", 60)).rejects.toBeInstanceOf(StoreRefusal);
  });
});

describe("ownership", () => {
  it("a folder is read by the session that staged it, and by nobody else", async () => {
    const { store, clock, held } = setup();
    const token = await held.put(folder());
    expect((await held.get(token))?.files).toEqual({ "release.yaml": "x" });
    // Another session of the same store: its list does not hold the token, whatever the store does.
    const other = heldBy(store, { auth: newRecord(provided(), clock()) }, clock);
    expect(await other.get(token)).toBeNull();
    // Planted: the same session's list, with the token a person made up or a prefix's other key.
    for (const made of [randomToken(), "../pages-session:x", `pages-session:${randomToken()}`, "", "x".repeat(200)]) {
      expect(await held.get(made)).toBeNull();
    }
  });

  it("a folder staged for one person is not read for another, even with the token in the list", async () => {
    const { store, clock, session } = setup("sub-a");
    const token = await heldBy(store, session, clock).put(folder("sub-a"));
    // The same list and key, but the session now belongs to someone else (a record written for another subject).
    const stranger = { auth: newRecord(provided("sub-b"), clock()), staged: [token] };
    expect(await heldBy(store, stranger, clock).get(token)).toBeNull();
  });

  it("a record that is not a folder is not one", async () => {
    const { store, clock, session } = setup();
    const token = randomToken();
    session.staged = [token];
    await store.set(`${STAGED_KEY_PREFIX}${token}`, JSON.stringify({ v: 1, subject: "sub-a" }), 60);
    expect(await heldBy(store, session, clock).get(token)).toBeNull();
    await store.set(`${STAGED_KEY_PREFIX}${token}`, "not json", 60);
    expect(await heldBy(store, session, clock).get(token)).toBeNull();
  });
});

describe("lifetime", () => {
  it("a folder is held for at most half an hour and never past the session, and goes when either ends", async () => {
    const { store, held, clock } = setup();
    const token = await held.put(folder());
    expect(store.ttl(`${STAGED_KEY_PREFIX}${token}`)).toBe(STAGED_TTL_SECONDS);
    clock.advance(STAGED_TTL_SECONDS + 1);
    expect(await held.get(token)).toBeNull();
  });

  it("with the session's own end nearer than half an hour, the folder's key ends with it; with none left, nothing is held", async () => {
    const clock = testClock();
    const store = new MemorySessionStore({ clock });
    const near = { ...provided(), idpSessionExpiresAt: clock() + 600 * 1000 };
    const session = { auth: newRecord(near, clock()), staged: undefined as string[] | undefined };
    const token = await heldBy(store, session, clock).put(folder());
    expect(store.ttl(`${STAGED_KEY_PREFIX}${token}`)).toBe(600);
    clock.advance(599.5);
    await expect(heldBy(store, session, clock).put(folder())).rejects.toMatchObject({ reason: "session" });
  });

  it("a session holds at most three, the oldest going from the store and the list", async () => {
    const { store, held, session } = setup();
    const tokens: string[] = [];
    for (let i = 0; i < MAX_HELD + 2; i += 1) tokens.push(await held.put(folder()));
    expect(session.staged).toEqual(tokens.slice(-MAX_HELD));
    expect(store.keys().filter((k) => k.startsWith(STAGED_KEY_PREFIX))).toHaveLength(MAX_HELD);
  });

  it("dropping a folder removes it and its token; ending the session removes every one", async () => {
    const { store, held, session } = setup();
    const a = await held.put(folder());
    const b = await held.put(folder());
    await held.drop(a);
    expect(session.staged).toEqual([b]);
    expect(store.keys().filter((k) => k.startsWith(STAGED_KEY_PREFIX))).toHaveLength(1);
    await endStaged(store, ["../x", "short", ...(session.staged ?? [])]);
    expect(store.keys().filter((k) => k.startsWith(STAGED_KEY_PREFIX))).toEqual([]);
  });

  it("a folder over what the store holds is refused in a way the page can word", async () => {
    const { held } = setup();
    // JSON turns each control character into six, so a folder under the file cap can still be over the store's limit.
    await expect(held.put(folder("sub-a", { "release.yaml": "\u0001".repeat(1024 * 1024) }))).rejects.toMatchObject({ reason: "size" });
    await expect(held.put(folder("sub-a", { "release.yaml": "\u0001".repeat(1024 * 1024) }))).rejects.toBeInstanceOf(StagedTooLarge);
  });
});

describe("an upload page", () => {
  const page = (over: Partial<PageModule>): PageModule => ({ id: "studio-releases", path: "/up", methods: ["GET", "POST"], handler: () => undefined, upload: true, ...over });
  const known = new Set(["studio-releases"]);

  it("is registered when it answers POST", () => {
    expect(() => registerPages([page({})], known)).not.toThrow();
  });

  it("is refused at start-up, in words, when it cannot take a POST", () => {
    expect(() => registerPages([page({ methods: ["GET"] })], known)).toThrow(/takes an upload but does not answer POST/);
  });
});
