/**
 * The Studio pages' test world (slice IS5a): the real app with the real page list, an in-memory store, a fake Conduit that
 * refuses what the real one refuses, and a sign-in whose bearer is the fake's person's. Synthetic throughout (rule 9).
 */
import { PAGES } from "../../server/pageList.js";
import type { IdentityProvider } from "../../server/identity.js";
import type { MemorySessionStore, SessionStore } from "../../server/sessionStore.js";
import { build } from "./build.js";
import type { Built } from "./build.js";
import { fakeConduit } from "./fakeConduit.js";
import type { CaseRow, FakeConduit, Person } from "./fakeConduit.js";
import { csrfFromPage, request, signIn } from "./http.js";
import { testClock } from "./clock.js";
import { generateSecret } from "./secret.js";
import type { Signed } from "./http.js";

export const DATASET = "harbour-extract";
export const DATASET_NAME = "Harbour prison extract (synthetic)";
export const CASE_ID = "case-harbour";

export function caseRow(over: Partial<CaseRow> = {}): CaseRow {
  return {
    id: CASE_ID,
    name: "Wing review",
    level: "author",
    created_at: "2026-11-01T09:00:00Z",
    created_by: "analyst-1",
    domains: ["niem"],
    datasets: [DATASET_NAME],
    dataset_ids: [DATASET],
    ...over,
  };
}

/** Made now, at random, held in memory and written nowhere: a bearer for the fake Conduit to know. */
export function bearer(): string {
  return `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`;
}

export const ALL_RIGHTS = ["edit_target_model", "publish_pipelines", "edit_pipelines", "accept_types", "run_pipelines", "add_ingest_files"];

export function person(over: Partial<Person> = {}): Person {
  return { token: bearer(), rights: ALL_RIGHTS, cases: [caseRow()], ...over };
}

export function providerFor(token: string, subject = "sub-studio-test"): IdentityProvider {
  return {
    async signIn() {
      return {
        subject,
        displayName: "Alex Example",
        accessToken: token,
        refreshToken: `refresh-${token}`,
        idpSessionExpiresAt: Date.now() + 10 * 3600 * 1000,
      };
    },
  };
}

export interface World extends Built {
  conduit: FakeConduit;
  me: Person;
  signed: Signed;
  logs: string[];
  /** A GET as the signed-in person. */
  get(url: string): ReturnType<ReturnType<typeof request>["get"]>;
  /** A url-encoded POST as the signed-in person, with the anti-forgery token unless `csrf` is `false` or text. */
  post(url: string, fields: Record<string, string>, csrf?: string | false): ReturnType<ReturnType<typeof request>["post"]>;
  stop(): Promise<void>;
}

export interface WorldOptions {
  /** How long the sign-in lasts by the app's own clock, in seconds, when a test wants the session's end to be near. */
  sessionSeconds?: number;
  /**
   * Keep the held folder apart from the session store, as a deployment does, and write down the key of every `set` the
   * session store is given into this list, so a test can show that no folder reaches it (the deployment's Valkey saves to disk).
   */
  sessionStoreWrites?: string[];
}

export async function world(me: Person = person(), others: Person[] = [], options: WorldOptions = {}): Promise<World> {
  const conduit = await fakeConduit([me, ...others]);
  const logs: string[] = [];
  const clock = testClock();
  const base = providerFor(me.token);
  const identityProvider: IdentityProvider =
    options.sessionSeconds === undefined
      ? base
      : {
          async signIn(...args) {
            const session = await base.signIn(...args);
            return { ...session, idpSessionExpiresAt: clock() + (options.sessionSeconds as number) * 1000 };
          },
        };
  const built = build({
    clock,
    pages: PAGES,
    ...(options.sessionStoreWrites
      ? {
          stagedApart: true,
          wrapStore: (inner: MemorySessionStore): SessionStore => {
            const writes = options.sessionStoreWrites as string[];
            return {
              get: (key) => inner.get(key),
              set: (key, value, ttl) => {
                writes.push(key);
                return inner.set(key, value, ttl);
              },
              expire: (key, ttl) => inner.expire(key, ttl),
              del: (key) => inner.del(key),
              take: (key) => inner.take(key),
            };
          },
        }
      : {}),
    identityProvider,
    forward: { conduitUrl: conduit.url, bodyMaxBytes: 1024 * 1024, uploadMaxBytes: 8 * 1024 * 1024, upstreamTimeoutSeconds: 5 },
    log: (message) => logs.push(message),
  });
  const signed = await signIn(built.app);
  const api = request(built.app);
  return {
    ...built,
    conduit,
    me,
    signed,
    logs,
    get: (url) => api.get(url).set("Cookie", signed.cookie),
    post: (url, fields, csrf) => {
      const token = csrf === false ? undefined : (csrf ?? signed.csrf);
      const body = token === undefined ? fields : { _csrf: token, ...fields };
      return api.post(url).set("Cookie", signed.cookie).type("form").send(body);
    },
    stop: () => conduit.stop(),
  };
}

export { csrfFromPage };

/** What a page says in its text: tags dropped, entities for the five characters undone, runs of space made one. */
export function textOf(html: string): string {
  return html
    .replace(/<script\b[\s\S]*?<\/script>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

/** Everything a person's browser, a proxy, a log or the store's key names could carry. */
export interface Observations {
  /** Each response's text and headers, in full. */
  responses: { text: string; headers: Record<string, unknown> }[];
  /** Every log line and everything written to the console. */
  logs: string[];
  /** The store's key names (never values: the staged bundle is the store's to hold). */
  keys: string[];
  /** Every address the browser was sent to or asked for. */
  urls: string[];
}

/** Where a planted marker is found, by place; empty when it is nowhere it must not be. */
export function findLeaks(marker: string, seen: Observations): string[] {
  const found: string[] = [];
  const has = (text: string): boolean => [marker, encodeURIComponent(marker), Buffer.from(marker).toString("base64")].some((form) => text.includes(form));
  seen.responses.forEach((r, i) => {
    if (has(r.text)) found.push(`response ${i} body`);
    if (has(JSON.stringify(r.headers))) found.push(`response ${i} headers`);
  });
  seen.logs.forEach((line, i) => has(line) && found.push(`log line ${i}`));
  seen.keys.forEach((key) => has(key) && found.push(`store key ${key}`));
  seen.urls.forEach((url) => has(url) && found.push(`address ${url}`));
  return found;
}
