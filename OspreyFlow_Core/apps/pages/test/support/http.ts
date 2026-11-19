import type { Express } from "express";
import request from "supertest";
import type { Response } from "supertest";

import { COOKIE_NAME } from "../../server/sessions.js";
import { SENTINEL_SUBJECT, SENTINEL_TOKENS } from "./fakeProvider.js";

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

export function idFrom(res: Pick<Response, "headers">): string {
  const mine = setCookies(res).find((c) => c.startsWith(`${COOKIE_NAME}=`));
  if (!mine) throw new Error("no session cookie was set");
  return mine.slice(COOKIE_NAME.length + 1).split(";")[0] as string;
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
  const cookie = `${COOKIE_NAME}=${id}`;
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
];

/**
 * Throws when a response carries a token. The rule (ADR-050 Amendment 4): no token in any body,
 * header or cookie but the one opaque identifier. Looks for each sentinel whole, in its pieces, and
 * URL-encoded or base64-encoded; any `eyJ…` token-shaped string; and any cookie that is not the
 * session identifier, or whose value is not a bare 32-byte base64url string.
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
    if (value !== "" && !/^[A-Za-z0-9_-]{43}$/.test(value)) throw new Error(`${where}: the cookie's value is not an opaque identifier`);
  }
}

export { request };
