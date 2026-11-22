/**
 * A release folder held between the Studio's Releases steps (slice IS5a).
 *
 * The React screen keeps the folder's files in component state across choose, check and import. A server-rendered page has no
 * such memory, so the folder is held on the server, in the store the session itself lives in, and the page's forms carry only
 * an opaque token.
 *
 * WHAT IS HELD. For one folder: the person's subject, the case and dataset it was read for, the folder's files (path and text,
 * the folder's own name taken off), and the result of the last check (whether it was clean, the version of the person's own
 * draft it named, whether they confirmed replacing it). A release can carry recipes and mappings, so it is held as little as
 * the steps need: nothing else of it is ever kept, and it is never rendered into a page, a URL, a cookie or a log line.
 * FOR HOW LONG. At most `STAGED_TTL_SECONDS` (half an hour) from the last step, and never past the session: the key's time to
 * live is the least of the two, so the store removes it when either ends. It is removed at once after a successful import and
 * when the person signs out (`endStaged`); a session holds at most `MAX_HELD` folders, and staging another removes the oldest.
 * HOW MUCH. `MAX_FOLDER_BYTES` of file text (2 MB) and `MAX_FOLDER_FILES` files; over either, nothing is held and the person
 * is told in words. The store refuses a value over `MAX_STAGED_VALUE_BYTES` as a second guard.
 * WHO CAN READ IT. Only the session that staged it: a token must be in the session's own list (`session.staged`) and the
 * record must name the session's own subject. A token that is another session's, made up, expired or already used reads as
 * "no longer held", in the same words, and says nothing of which it was.
 * NEVER WRITTEN TO DISK. The folder is held in the pages process's own memory (`createApp`'s `stagedStore`, a
 * `MemorySessionStore`), not in the session's store: the deployment's Valkey keeps its built-in save points and snapshots its
 * keys to disk, so `ValkeySessionStore` refuses this prefix, and a test (`studioReleasesRound4.test.ts`) shows that no folder
 * key reaches the session store. The cost: a folder is lost when the pages process restarts (the person is told it is no longer
 * held and chooses the folder again), and a second pages process would not see the first's folders.
 */
import type { SessionRecord } from "./sessionPolicy.js";
import { randomToken, ttlSeconds } from "./sessionPolicy.js";
import { MAX_STAGED_VALUE_BYTES, STAGED_KEY_PREFIX } from "./sessionStore.js";
import type { SessionStore } from "./sessionStore.js";

export const STAGED_TTL_SECONDS = 30 * 60;
export const MAX_FOLDER_BYTES = 2 * 1024 * 1024;
export const MAX_FOLDER_FILES = 200;
export const MAX_HELD = 3;

/** The folder's last check, as the steps after it need it. */
export interface StagedCheck {
  /** The check found nothing wrong: the import may be offered. */
  clean: boolean;
  /** The version of the person's own in-progress draft the check named, when it named one. */
  ownDraftVersion: number | null;
  /** The person has ticked "replace my draft": the next call carries the version above. */
  confirmed: boolean;
}

export interface Staged {
  v: 1;
  subject: string;
  caseId: string;
  datasetId: string;
  files: Record<string, string>;
  check?: StagedCheck;
}

/**
 * A folder that cannot be held: said in words, nothing held. `reason` says which words: "size" is a folder over what the store
 * holds; "session" is a session with under a second left, which is not a fault of the folder.
 */
export class StagedTooLarge extends Error {
  constructor(
    message: string,
    readonly reason: "size" | "session" = "size",
  ) {
    super(message);
  }
}

const TOKEN = /^[A-Za-z0-9_-]{43}$/;

function keyFor(token: string): string {
  return `${STAGED_KEY_PREFIX}${token}`;
}

function isStaged(value: unknown): value is Staged {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    r["v"] === 1 &&
    typeof r["subject"] === "string" &&
    typeof r["caseId"] === "string" &&
    typeof r["datasetId"] === "string" &&
    typeof r["files"] === "object" &&
    r["files"] !== null
  );
}

/** The same session's held folders, for a request (and the clock the store's expiry runs on). */
export interface Held {
  put(folder: Staged): Promise<string>;
  /** The folder this token names, when it is this session's, for this person, and still held; otherwise null. */
  get(token: string): Promise<Staged | null>;
  /** Writes the folder again (a check's result) and gives it half an hour more, never past the session. */
  save(token: string, folder: Staged): Promise<void>;
  /** Removes the folder, and the token from the session's list. */
  drop(token: string): Promise<void>;
}

/** The session's own held folders. `session` is the request's: its `staged` list is read and written through it. */
export function heldBy(
  store: SessionStore,
  session: { auth?: SessionRecord; staged?: string[] },
  clock: () => number,
): Held {
  const auth = (): SessionRecord => {
    if (!session.auth) throw new Error("a folder is held only for a signed-in session");
    return session.auth;
  };
  const lifetime = (): number => Math.min(STAGED_TTL_SECONDS, ttlSeconds(auth(), clock()));
  const write = async (token: string, folder: Staged): Promise<void> => {
    const ttl = lifetime();
    if (ttl < 1) throw new StagedTooLarge("the session is about to end", "session");
    const text = JSON.stringify(folder);
    if (Buffer.byteLength(text, "utf8") > MAX_STAGED_VALUE_BYTES) throw new StagedTooLarge("over the store's limit");
    await store.set(keyFor(token), text, ttl);
  };
  return {
    async put(folder) {
      const token = randomToken();
      await write(token, folder);
      const held = [...(session.staged ?? []), token];
      // At most MAX_HELD: the oldest goes, from the store and from the list.
      while (held.length > MAX_HELD) {
        const oldest = held.shift() as string;
        await store.del(keyFor(oldest));
      }
      session.staged = held;
      return token;
    },
    async get(token) {
      if (!TOKEN.test(token) || !(session.staged ?? []).includes(token)) return null;
      const raw = await store.get(keyFor(token));
      if (raw === null) return null;
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = undefined;
      }
      if (!isStaged(parsed) || parsed.subject !== auth().subject) return null;
      return parsed;
    },
    async save(token, folder) {
      if (!TOKEN.test(token) || !(session.staged ?? []).includes(token)) return;
      await write(token, folder);
    },
    async drop(token) {
      if (!TOKEN.test(token)) return;
      await store.del(keyFor(token));
      session.staged = (session.staged ?? []).filter((held) => held !== token);
    },
  };
}

/** Removes every folder a session holds: its sign-out. A token that is not one of ours is skipped. */
export async function endStaged(store: SessionStore, tokens: readonly string[] | undefined): Promise<void> {
  for (const token of tokens ?? []) {
    if (TOKEN.test(token)) await store.del(keyFor(token));
  }
}
