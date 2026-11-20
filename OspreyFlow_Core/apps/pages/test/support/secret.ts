import { randomBytes } from "node:crypto";

/**
 * A session-signing secret made now, at run time: random, exactly `length` characters (at least 32 by
 * default), held in memory for the one test run and written nowhere. A test never writes the setting's
 * value in its own source (the owner's rule for `OSPREY_PAGES_SESSION_SECRET`, 19 November 2026).
 */
export function generateSecret(length = 48): string {
  let out = "";
  while (out.length < length) out += randomBytes(48).toString("base64url");
  return out.slice(0, length);
}
