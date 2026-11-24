/**
 * The Studio pages' own calls to the Conduit, as the person (slice IS5a; ADR-152 decision 5).
 *
 * A server-rendered page reads and writes through the same door a script's call takes (`forward.ts`): the Conduit's address is
 * the forwarder's setting (`OSPREY_PAGES_CONDUIT_URL`), the bearer is the person's, from `accessTokenFor`, and the Conduit
 * authorises every route itself (rules 3 and 4): this adds no access rule of its own, and the page's words about a right are
 * words only. What is sent is built here, one header at a time: `Authorization`, `Accept` and, for a JSON body, `Content-Type`.
 * Nothing the browser sent goes on: not its cookie, its anti-forgery token, its address or its headers. A redirect is never
 * followed. The path is made from segments each encoded as one piece (`v1`), so a dataset's name cannot change the route.
 *
 * Nothing is logged here but a fixed phrase and a status: not a body (a release folder can hold recipes and mappings), not a
 * token, not an address.
 */
import { accessTokenFor } from "./accessToken.js";
import type { ForwardSettings } from "./config.js";
import type { SessionRecord } from "./sessionPolicy.js";

export interface Reply {
  status: number;
  /** The body as JSON, or `undefined` when it was not. */
  json: unknown;
  /** The body as text: a release's file is text. */
  text: string;
}

export interface Call {
  /** `PUT` and `DELETE` are the draft's (slice IS2a): a save and a discard, each carrying the version the person's copy was read at. */
  method?: "GET" | "POST" | "PUT" | "DELETE";
  /** A path made by `v1`. */
  path: string;
  query?: Record<string, string | number | boolean>;
  json?: unknown;
}

/** The Conduit could not be reached, or gave no answer in time. The reason is never kept: it could name an address. */
export class ConduitUnreachable extends Error {
  override name = "ConduitUnreachable";
}

/** `/v1/` and each segment encoded as one piece. */
export function v1(...segments: string[]): string {
  return `/v1/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
}

export type Conduit = (call: Call) => Promise<Reply>;

export async function conduitFor(
  settings: ForwardSettings,
  auth: SessionRecord,
  log: (message: string) => void = () => undefined,
): Promise<Conduit> {
  const token = await accessTokenFor(auth);
  const base = new URL(settings.conduitUrl);
  return async (call) => {
    const url = new URL(call.path, base);
    for (const [key, value] of Object.entries(call.query ?? {})) url.searchParams.set(key, String(value));
    const headers: Record<string, string> = { Authorization: `Bearer ${token}`, Accept: "application/json" };
    let body: string | undefined;
    if (call.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(call.json);
    }
    let response: Response;
    try {
      response = await fetch(url, {
        method: call.method ?? "GET",
        headers,
        ...(body === undefined ? {} : { body }),
        redirect: "manual",
        signal: AbortSignal.timeout(settings.upstreamTimeoutSeconds * 1000),
      });
    } catch {
      log("pages: studio: the Conduit could not be reached (502)");
      throw new ConduitUnreachable();
    }
    let text: string;
    try {
      text = await response.text();
    } catch {
      log("pages: studio: the Conduit's answer could not be read (502)");
      throw new ConduitUnreachable();
    }
    let json: unknown;
    try {
      json = JSON.parse(text);
    } catch {
      json = undefined;
    }
    if (response.status >= 500) log(`pages: studio: the Conduit answered ${response.status}`);
    return { status: response.status, json, text };
  };
}
