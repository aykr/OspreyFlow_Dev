// ADR-148 Amendment 8: what the Glass shows and gates on is the Conduit's resolved principal (`GET /v1/me`),
// never a claim of a token. On Entra ID a token's `roles` are app roles an Entra administrator assigns, and
// its subject is not the principal's id. The source check below fails if a token's role or access claim is
// read anywhere in the Glass again; it is shown to catch each shape it looks for.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { displayPrincipal, fetchResolvedPrincipal, sessionFromUser } from "./userManager";

afterEach(() => vi.unstubAllGlobals());

const ME = { id: "50000000-0000-4000-8000-000000000001", clearance: "OFFICIAL", org_unit: "unit-1", roles: ["analyst"],
             receivable_handling_codes: ["R"] };  // prettier-ignore

describe("the session from the ID token", () => {
  it("carries the subject and the names, and no role or access claim", () => {
    const session = sessionFromUser({
      profile: { sub: "pairwise", preferred_username: "ana", given_name: "Ana", roles: ["osprey-admin"],
                 clearance: "SECRET", org_unit: "u", receivable_handling_codes: ["X"] },  // prettier-ignore
    } as never);
    expect(session).toEqual({ sub: "pairwise", username: "ana", givenName: "Ana" });
  });
});

describe("the principal shown", () => {
  it("takes its id, clearance, unit, roles and codes from the Conduit and only the names from the session", () => {
    const shown = displayPrincipal({ sub: "pairwise", username: "ana", givenName: "Ana" }, ME);
    expect(shown).toEqual({ sub: ME.id, username: "ana", givenName: "Ana", clearance: "OFFICIAL", orgUnit: "unit-1",
                            roles: ["analyst"], receivableHandlingCodes: ["R"] });  // prettier-ignore
  });
});

describe("GET /v1/me", () => {
  it.each([
    ["a refusal", () => new Response("{}", { status: 503 })],
    ["a body that is not a principal", () => new Response(JSON.stringify({ roles: ["osprey-admin"] }))],
    ["no answer", () => Promise.reject(new TypeError("network"))],
  ])("is none after %s, never a guess", async (_why, answer) => {
    vi.stubGlobal("fetch", vi.fn(async () => answer()));
    expect(await fetchResolvedPrincipal("http://x", "t")).toBeNull();
  });

  it("asks with the bearer and reads the answer", async () => {
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify(ME)));
    vi.stubGlobal("fetch", fetchSpy);
    expect(await fetchResolvedPrincipal("http://x", "t")).toEqual(ME);
    expect(fetchSpy).toHaveBeenCalledWith("http://x/v1/me", { headers: { Authorization: "Bearer t" } });
  });
});

// --- no token claim of role or access is read in the Glass ---

const CLAIMS = "roles|clearance|org_unit|receivable_handling_codes";
const READ = new RegExp(String.raw`profile\??\.(${CLAIMS})\b|profile\??\[\s*["'\x60](${CLAIMS})["'\x60]\s*\]|\{[^}]*\b(${CLAIMS})\b[^}]*\}\s*=\s*[\w.?]*profile\b`);
const SRC = join(__dirname, "..");

/** A claim read through a name the profile was given (`const c = user.profile; c.roles`), as well as
 * through `profile` itself (the lane-reviewer's finding 14). */
function readsAClaim(source: string): boolean {
  if (READ.test(source)) return true;
  const aliases = [...source.matchAll(/(?:const|let|var)\s+(\w+)\s*=\s*[\w.?]*\bprofile\b/g)].map((m) => m[1]);
  return aliases.some((alias) => new RegExp(String.raw`\b${alias}\??\.(${CLAIMS})\b|\b${alias}\??\[\s*["'\x60](${CLAIMS})`).test(source));
}

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

describe("no token claim of role or access is read in the Glass", () => {
  it("is read nowhere in apps/workspace/src", () => {
    const found = sources(SRC)
      .filter((path) => readsAClaim(readFileSync(path, "utf8")))
      .map((path) => relative(SRC, path));
    expect(found).toEqual([]);
  });

  it.each([
    "String(profile.roles ?? '')",
    "user.profile?.clearance",
    'profile["org_unit"]',
    "profile[`receivable_handling_codes`]",
    "const { roles } = user.profile;",
    "const c = user.profile; return c.roles;",
    "let p = session?.profile;\nconst level = p?.clearance;",
  ])("catches %s", (planted) => {
    expect(readsAClaim(planted)).toBe(true);
  });

  it("does not catch the names", () => {
    expect(readsAClaim("String(profile.preferred_username ?? '')")).toBe(false);
    expect(readsAClaim("const c = user.profile; return c.preferred_username;")).toBe(false);
  });
});
