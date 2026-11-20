/**
 * What is kept between the start of a sign-in and its callback (ADR-152 decision 4, slice PL9a), and the
 * cookie that finds it.
 *
 * Before a session exists a callback could be forged: a page of an attacker's making can send a victim's
 * browser to `/session/callback` with the attacker's own `code` (login CSRF). So the start stores
 * `{state, nonce, verifier, returnTo}` on the server, single use, ten minutes, and sets a short-lived signed
 * cookie holding only the random identifier of that record. The callback must present the cookie, the record
 * must exist, and `state` must match; the record is deleted when it is read, so a second use is refused.
 */
import { createHmac, timingSafeEqual } from "node:crypto";

import type { PendingLogin } from "./identity.js";

export const LOGIN_COOKIE_NAME = "osprey_pages_login";
export const LOGIN_TTL_SECONDS = 10 * 60;

/** Only the callback needs it, so only `/session` is sent it. `Secure`, `HttpOnly`, `SameSite=Lax`, no `Domain`. */
export const LOGIN_COOKIE_OPTIONS = { httpOnly: true, secure: true, sameSite: "lax", path: "/session" } as const;

/** What the start keeps on the server. The verifier is the one secret in it. */
export interface LoginRecord extends PendingLogin {
  v: 1;
  /** A path inside the application, already checked by `safeReturnTo`. */
  returnTo: string;
  createdAt: number;
}

export function isLoginRecord(value: unknown): value is LoginRecord {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    r["v"] === 1 &&
    typeof r["state"] === "string" &&
    r["state"] !== "" &&
    typeof r["nonce"] === "string" &&
    r["nonce"] !== "" &&
    typeof r["verifier"] === "string" &&
    r["verifier"] !== "" &&
    typeof r["returnTo"] === "string" &&
    typeof r["createdAt"] === "number"
  );
}

const ID_PATTERN = /^[A-Za-z0-9_-]{43}$/;
const SIGNATURE_PATTERN = /^[A-Za-z0-9_-]{43}$/;

/** HMAC-SHA256 of the identifier under a label of its own, so a signature made for a session cookie is not one for this. */
function signature(id: string, secret: string): string {
  return createHmac("sha256", secret).update(`pages-login:${id}`).digest("base64url");
}

/** `<identifier>.<signature>`: the cookie's value. */
export function signLoginId(id: string, secret: string): string {
  return `${id}.${signature(id, secret)}`;
}

/** The identifier in the request's login cookie, or null when there is none or its signature is not ours. */
export function readLoginId(cookieHeader: string | undefined, secret: string): string | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(";")) {
    const at = part.indexOf("=");
    if (at < 0 || part.slice(0, at).trim() !== LOGIN_COOKIE_NAME) continue;
    const value = part.slice(at + 1).trim();
    const [id, sig, ...rest] = value.split(".");
    if (rest.length > 0 || id === undefined || sig === undefined) return null;
    if (!ID_PATTERN.test(id) || !SIGNATURE_PATTERN.test(sig)) return null;
    const expected = Buffer.from(signature(id, secret));
    const given = Buffer.from(sig);
    return given.length === expected.length && timingSafeEqual(given, expected) ? id : null;
  }
  return null;
}

/** Equal, non-empty strings, compared without stopping at the first difference. */
export function sameValue(given: unknown, expected: string): boolean {
  if (typeof given !== "string" || given === "" || expected === "") return false;
  const a = createHmac("sha256", "pages-login-compare").update(given).digest();
  const b = createHmac("sha256", "pages-login-compare").update(expected).digest();
  return timingSafeEqual(a, b);
}

const BASE = "https://application.invalid";

/**
 * Where to send the person after sign-in: a path inside the application, or the home page. A single leading
 * `/` not followed by another `/` or a `\`, no backslash or control character anywhere (a browser reads
 * `/\evil` and `/<tab>/evil` as `//evil`), and nothing that a URL parser takes to another origin. Anything
 * else, including a missing or repeated parameter, is dropped to `/`.
 */
export function safeReturnTo(raw: unknown): string {
  if (typeof raw !== "string" || raw === "" || raw.length > 2048) return "/";
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/";
  // eslint-disable-next-line no-control-regex
  if (/[\\\u0000-\u001f\u007f]/.test(raw)) return "/";
  try {
    if (new URL(raw, BASE).origin !== BASE) return "/";
  } catch {
    return "/";
  }
  return raw;
}
