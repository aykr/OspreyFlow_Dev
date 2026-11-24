/**
 * The page service's own start-up checks, run on every address the deployment's render derives (build id PL7, slice
 * PL7f; the owner's ruling of 24 November 2026).
 *
 * The deployment's renderer works out the service's issuer, public origin, identity alias and trust in one place
 * (`harness/page_addresses.py`'s `derive`) and writes a table of cases that the owner approved: one row per case, the
 * configuration and the values derived or the refusal. This test reads the same table as the two Python tests
 * (`page_addresses_cases.json`, in the sibling folder that holds the deployment's tests) and calls the service's own
 * `loadConfig` for every derived row. `loadConfig` is what runs `publicOrigin()`, `oidcSettings()` and `addressSetting`
 * (config.ts); none of it is re-implemented here, so a value the real service refuses fails this test. Round 8 of the
 * earlier work went wrong because a Python stand-in for these checks accepted `https://host:443`, which the real
 * check refuses (`raw !== new URL(raw).origin`).
 *
 * It needs no build: vitest reads `config.ts` as it is. What it walks: one file, the table, and the service's config.
 * Where the table is not beside this checkout (the product's own repository carries no deployment tests) the test
 * skips, in words; inside the monorepo a table that cannot be found fails.
 */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { loadConfig } from "../../server/config.js";
import { generateSecret } from "../support/secret.js";

interface Derived {
  public_origin: string;
  identity: string;
  issuer: string;
  identity_alias: string;
  identity_port: number;
  extra_listener: number | null;
  trust: string | null;
  environment: Record<string, string>;
}

interface Row {
  case: number;
  id: string;
  expect: { derived?: Derived; refuse?: { key: string }; off?: boolean };
}

interface Table {
  secret_variable: string;
  rows: Row[];
}

const here = path.dirname(fileURLToPath(import.meta.url));
/** `apps/pages/test/server` is five folders below the repository's root. */
const root = path.resolve(here, "../../../../..");
const TABLE_AT = path.join("tests", "fixtures", "page_addresses_cases.json");

/** The table, in whichever sibling folder of the product holds it; undefined outside the monorepo. */
function findTable(): string | undefined {
  if (!existsSync(path.join(root, "OspreyFlow_Core", "apps", "pages"))) return undefined;
  for (const name of readdirSync(root)) {
    const candidate = path.join(root, name, TABLE_AT);
    if (name !== "OspreyFlow_Core" && existsSync(candidate)) return candidate;
  }
  throw new Error(
    "the table of cases (tests/fixtures/page_addresses_cases.json) is in no sibling of OspreyFlow_Core: " +
      "the page service's addresses are checked against it, so this test cannot run without it",
  );
}

const tablePath = findTable();
const describeTable = tablePath === undefined ? describe.skip : describe;
const table: Table = tablePath === undefined ? { secret_variable: "", rows: [] } : JSON.parse(readFileSync(tablePath, "utf8"));
const derivedRows = table.rows.filter((row) => row.expect.derived !== undefined);

/** What the container is given for a derived row: the derived variables, the secrets made now, the Conduit's address. */
function environmentOf(derived: Derived): Record<string, string> {
  return {
    ...derived.environment,
    [table.secret_variable]: generateSecret(),
    OSPREY_PAGES_SESSION_SECRET: generateSecret(),
    OSPREY_PAGES_CONDUIT_URL: "http://api:9001",
  };
}

describeTable("the page service starts on every address the render derives", () => {
  it("has a derived row for the cases the service's own checks matter to", () => {
    const cases = new Set(derivedRows.map((row) => row.case));
    for (const wanted of [3, 4, 7, 10, 11, 12, 14, 15, 16]) expect(cases, `case ${wanted}`).toContain(wanted);
    expect(derivedRows.length).toBeGreaterThan(10);
  });

  it.each(derivedRows.map((row) => [row.id, row] as const))("%s: loadConfig accepts it", (_id, row) => {
    const derived = row.expect.derived as Derived;
    const config = loadConfig(environmentOf(derived));
    // The service reads back what was derived: the sign-in's issuer and the origin that names its callback,
    // and the live-updates proxy's `Origin` to compare with. A value it altered would show here.
    expect(config.oidc?.issuer).toBe(derived.issuer);
    expect(config.oidc?.publicOrigin).toBe(derived.public_origin);
    expect(config.stream?.publicOrigin).toBe(derived.public_origin);
    // The origin is its own `URL.origin`: no default port, lower case, no path (the check `publicOrigin()` makes).
    expect(new URL(derived.public_origin).origin).toBe(derived.public_origin);
    // The issuer carries the identity address and the realm, and the identity address is the origin's own host
    // with `id.` in front: the service checks the discovery document's `issuer` against the address it asked.
    expect(derived.issuer).toBe(`${derived.identity}/realms/osprey`);
    expect(new URL(derived.identity).hostname).toBe(derived.identity_alias);
    expect(new URL(derived.identity).hostname).toBe(`id.${new URL(derived.public_origin).hostname}`);
    expect(new URL(derived.identity).port).toBe(new URL(derived.public_origin).port);
    expect(new URL(derived.identity).protocol).toBe("https:");
  });

  /**
   * The test is shown red against values the service refuses, each in the shape the render writes (the derived
   * environment of a real row with one value changed), so a green result is not the check having nothing to say.
   */
  describe("is red for a value the real service refuses", () => {
    const row = derivedRows.find((candidate) => candidate.id === "3-acme-default-port");
    const derived = (row?.expect.derived ?? ({ environment: {} } as unknown)) as Derived;

    it("a default port left on the origin", () => {
      expect(() => loadConfig(environmentOf(derived))).not.toThrow();
      const planted = { ...environmentOf(derived), OSPREY_PAGES_PUBLIC_ORIGIN: `${derived.public_origin}:443` };
      expect(() => loadConfig(planted)).toThrow(/must be the origin alone/);
    });

    it("an upper-case host", () => {
      const planted = { ...environmentOf(derived), OSPREY_PAGES_PUBLIC_ORIGIN: derived.public_origin.toUpperCase() };
      expect(() => loadConfig(planted)).toThrow(/OSPREY_PAGES_PUBLIC_ORIGIN/);
    });

    it("an identity address over plain HTTP that is not loopback", () => {
      const planted = { ...environmentOf(derived), OSPREY_PAGES_OIDC_ISSUER: derived.issuer.replace("https:", "http:") };
      expect(() => loadConfig(planted)).toThrow(/must be an https address/);
    });

    it("an origin with a path, and one that carries a user name", () => {
      const withPath = { ...environmentOf(derived), OSPREY_PAGES_PUBLIC_ORIGIN: `${derived.public_origin}/app` };
      expect(() => loadConfig(withPath)).toThrow(/must be the origin alone/);
      const withUser = { ...environmentOf(derived), OSPREY_PAGES_PUBLIC_ORIGIN: "https://user:pw@osprey.example.org" };
      expect(() => loadConfig(withUser)).toThrow(/user name or password/);
    });

    it("an issuer that is not an address, and a sign-in with no secret", () => {
      const notAnAddress = { ...environmentOf(derived), OSPREY_PAGES_OIDC_ISSUER: "id.osprey.example.org/realms/osprey" };
      expect(() => loadConfig(notAnAddress)).toThrow(/OSPREY_PAGES_OIDC_ISSUER/);
      const noSecret = { ...environmentOf(derived) };
      delete noSecret[table.secret_variable];
      expect(() => loadConfig(noSecret)).toThrow(/is required/);
    });
  });
});
