import { createHmac } from "node:crypto";

import type { Express } from "express";
import supertest from "supertest";
import type { Response, Test } from "supertest";

import { COOKIE_NAME } from "../../server/sessionPolicy.js";
import { SENTINEL_SUBJECT, SENTINEL_TOKENS } from "./fakeProvider.js";

/** A fixed dummy, never a real secret: the signing secret every test app is built with. */
export const TEST_SESSION_SECRET = "dummy-session-secret-for-tests-only-0123456789abcdef";

type Method = "get" | "post" | "put" | "patch" | "delete" | "head" | "options";

/**
 * A request as the front proxy delivers it: the proxy terminates TLS and says so in `X-Forwarded-Proto`
 * (ADR-152 decision 4: the cookie is `Secure`, and `express-session` sets a `Secure` cookie only on a
 * request it believes arrived over TLS). Without it a test over plain HTTP would see no cookie at all.
 */
export function request(app: Parameters<typeof supertest>[0]): Record<Method, (url: string) => Test> {
  const agent = supertest(app);
  const viaProxy = (method: Method) => (url: string) => agent[method](url).set("X-Forwarded-Proto", "https");
  return {
    get: viaProxy("get"),
    post: viaProxy("post"),
    put: viaProxy("put"),
    patch: viaProxy("patch"),
    delete: viaProxy("delete"),
    head: viaProxy("head"),
    options: viaProxy("options"),
  };
}

export interface Signed {
  /** The `Cookie` request header value, as a browser would send it. */
  cookie: string;
  id: string;
  csrf: string;
}

/** The `Set-Cookie` headers of a response, as a list. */
export function setCookies(res: Pick<Response, "headers">): string[] {
  const raw = res.headers["set-cookie"] as unknown;
  if (raw === undefined) return [];
  return Array.isArray(raw) ? (raw as string[]) : [String(raw)];
}

/** The `name=value` pair of the session cookie in a response, as a browser sends it back. */
export function cookieFrom(res: Pick<Response, "headers">): string {
  const mine = setCookies(res).find((c) => c.startsWith(`${COOKIE_NAME}=`));
  if (!mine) throw new Error("no session cookie was set");
  return mine.split(";")[0] as string;
}

/** The cookie's value alone, as sent: express-session's `s:<identifier>.<signature>`, URL-encoded. */
export function cookieValueFrom(res: Pick<Response, "headers">): string {
  return cookieFrom(res).slice(COOKIE_NAME.length + 1);
}

/** The session identifier inside the signed cookie: what the store's key is named after. */
export function idFrom(res: Pick<Response, "headers">): string {
  return unsigned(cookieValueFrom(res)).id;
}

/** Splits `s:<id>.<signature>`, which is what express-session writes; throws on anything else. */
export function unsigned(value: string): { id: string; signature: string } {
  const decoded = decodeURIComponent(value);
  const m = /^s:([A-Za-z0-9_-]{43})\.([A-Za-z0-9+/]{43})$/.exec(decoded);
  if (!m) throw new Error("the cookie is not a signed session identifier");
  return { id: m[1] as string, signature: m[2] as string };
}

/** The signature `cookie-signature` makes: HMAC-SHA256 of the identifier, base64 with no padding. */
export function signatureFor(id: string, secret: string = TEST_SESSION_SECRET): string {
  return createHmac("sha256", secret).update(id).digest("base64").replace(/=+$/, "");
}

/** A cookie value as express-session would sign it, for an identifier and a secret. */
export function signedCookie(id: string, secret: string = TEST_SESSION_SECRET): string {
  return `${COOKIE_NAME}=${encodeURIComponent(`s:${id}.${signatureFor(id, secret)}`)}`;
}

export function csrfFromPage(html: string): string {
  const m = /<input type="hidden" name="_csrf" value="([^"]+)"/.exec(html);
  if (!m) throw new Error("the page carries no anti-forgery token");
  return m[1] as string;
}

/**
 * Signs in through the real route and reads the token off the real page: the cookie header goes
 * as a browser sends it (a `Secure` cookie is not sent back over this test's plain HTTP by a
 * cookie jar, so the header is set by hand), the token comes from the form the page renders.
 */
export async function signIn(app: Express): Promise<Signed> {
  const res = await request(app).get("/session/sign-in");
  if (res.status !== 302) throw new Error(`sign-in answered ${res.status}`);
  const id = idFrom(res);
  const cookie = cookieFrom(res);
  const page = await request(app).get("/").set("Cookie", cookie);
  return { cookie, id, csrf: csrfFromPage(page.text) };
}

/** `Content-Security-Policy` as a directive-name to value map. */
export function parsePolicy(header: string | undefined): Map<string, string> {
  const out = new Map<string, string>();
  for (const part of (header ?? "").split(";")) {
    const piece = part.trim();
    if (!piece) continue;
    const [name, ...rest] = piece.split(/\s+/);
    out.set(name as string, rest.join(" "));
  }
  return out;
}

export function nonceOf(header: string | undefined): string {
  const m = /'nonce-([^']+)'/.exec(header ?? "");
  if (!m) throw new Error("no nonce in the policy");
  return m[1] as string;
}

/** Everything in a response a person's browser, a proxy or a log could see. */
export function everythingIn(res: Pick<Response, "headers" | "text">): string {
  const lines = Object.entries(res.headers).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join("\n") : String(v)}`);
  return `${lines.join("\n")}\n\n${res.text ?? ""}`;
}

export const SECRET_PARTS: string[] = [
  ...Object.values(SENTINEL_TOKENS).flatMap((t) => [t, ...t.split(".").filter((p) => p.length >= 8)]),
  SENTINEL_SUBJECT,
  TEST_SESSION_SECRET,
];

/**
 * Throws when a response carries a token. The rule (ADR-050 Amendment 4): no token in any body,
 * header or cookie but the one opaque identifier. Looks for each sentinel whole, in its pieces, and
 * URL-encoded or base64-encoded; any `eyJ…` token-shaped string; and any cookie that is not the
 * session cookie, or whose value is not express-session's signed identifier (`s:<43 characters>.<signature>`).
 */
export function assertNoTokenLeak(res: Pick<Response, "headers" | "text">, where: string): void {
  const haystack = everythingIn(res);
  for (const secret of SECRET_PARTS) {
    for (const form of [secret, encodeURIComponent(secret), Buffer.from(secret).toString("base64"), Buffer.from(secret).toString("base64url")]) {
      if (haystack.includes(form)) throw new Error(`${where}: a secret (${secret.slice(0, 24)}…) is in the response`);
    }
  }
  if (/eyJ[A-Za-z0-9_-]{8,}\./.test(haystack)) throw new Error(`${where}: a token-shaped string is in the response`);
  for (const cookie of setCookies(res)) {
    const [pair] = cookie.split(";");
    const [name, value = ""] = (pair as string).split("=");
    if (name !== COOKIE_NAME) throw new Error(`${where}: a cookie other than the session identifier: ${name}`);
    if (value !== "") {
      try {
        unsigned(value);
      } catch {
        throw new Error(`${where}: the cookie's value is not a signed opaque identifier`);
      }
    }
  }
}

