/** The service's own database number: not the Conduit's, which holds its working sets in db 0. */
import { describe, expect, it } from "vitest";

import { loadConfig } from "../../server/config.js";
import { valkeyOptions } from "../../server/valkey.js";

const SECRET = "dummy-session-secret-for-tests-only-0123456789abcdef";

describe("loadConfig", () => {
  it("defaults to port 8090 and Valkey database 1", () => {
    const config = loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET });
    expect(config.port).toBe(8090);
    expect(config.valkey.db).toBe(1);
    expect(config.valkey.host).toBe("localhost");
    expect(config.valkey.port).toBe(6379);
  });

  it("takes the database number from OSPREY_PAGES_VALKEY_DB", () => {
    expect(loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET, OSPREY_PAGES_VALKEY_DB: "4" }).valkey.db).toBe(4);
  });

  it.each(["0", "-1", "abc", "1.5", "", "99999"])("refuses %j as the database number", (value) => {
    expect(() => loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET, OSPREY_PAGES_VALKEY_DB: value })).toThrow(/OSPREY_PAGES_VALKEY_DB/);
  });

  it("refuses the Conduit's own database, wherever the Conduit has been told to put it", () => {
    expect(() => loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET, VALKEY_DB: "1" })).toThrow(/Conduit/);
    expect(() => loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET, VALKEY_DB: "3", OSPREY_PAGES_VALKEY_DB: "3" })).toThrow(/Conduit/);
    expect(loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET, VALKEY_DB: "0", OSPREY_PAGES_VALKEY_DB: "1" }).valkey.db).toBe(1);
  });

  it("reads the Conduit's Valkey settings, by the Conduit's own names", () => {
    const config = loadConfig({
      OSPREY_PAGES_SESSION_SECRET: SECRET,
      VALKEY_HOST: "valkey",
      VALKEY_PORT: "6380",
      VALKEY_PASSWORD: "pw",
      VALKEY_TLS: "true",
    });
    expect(config.valkey).toMatchObject({ host: "valkey", port: 6380, password: "pw", tls: true });
  });
});

describe("the session signing secret", () => {
  it("is read from OSPREY_PAGES_SESSION_SECRET", () => {
    expect(loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET }).sessionSecret).toBe(SECRET);
  });

  it("is required: no secret, no service", () => {
    expect(() => loadConfig({})).toThrow(/OSPREY_PAGES_SESSION_SECRET/);
    expect(() => loadConfig({ OSPREY_PAGES_SESSION_SECRET: "" })).toThrow(/OSPREY_PAGES_SESSION_SECRET/);
  });

  it("is at least 32 characters: 31 is refused and 32 is accepted", () => {
    expect(() => loadConfig({ OSPREY_PAGES_SESSION_SECRET: "x".repeat(31) })).toThrow(/at least 32/);
    expect(loadConfig({ OSPREY_PAGES_SESSION_SECRET: "x".repeat(32) }).sessionSecret).toHaveLength(32);
  });

  it("is never in a message that refuses something else, or in one that refuses it", () => {
    const short = "short-secret-value-17";
    for (const env of [
      { OSPREY_PAGES_SESSION_SECRET: short },
      { OSPREY_PAGES_SESSION_SECRET: SECRET, OSPREY_PAGES_VALKEY_DB: "99" },
      { OSPREY_PAGES_SESSION_SECRET: SECRET, VALKEY_DB: "1" },
    ]) {
      let message = "";
      try {
        loadConfig(env);
      } catch (error) {
        message = (error as Error).message;
      }
      expect(message).not.toBe("");
      expect(message).not.toContain(short);
      expect(message).not.toContain(SECRET);
    }
  });

  it("is not in the Valkey client's options, which are logged on a connection error", () => {
    const options = valkeyOptions(loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET }));
    expect(JSON.stringify(options)).not.toContain(SECRET);
  });
});

describe("valkeyOptions: what reaches the client", () => {
  const withSecret = (env: NodeJS.ProcessEnv) => loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET, ...env });

  it("sets db from OSPREY_PAGES_VALKEY_DB, and by default to 1, never the Conduit's 0", () => {
    expect(valkeyOptions(withSecret({})).db).toBe(1);
    expect(valkeyOptions(withSecret({ OSPREY_PAGES_VALKEY_DB: "6" })).db).toBe(6);
    expect(valkeyOptions(withSecret({ OSPREY_PAGES_VALKEY_DB: "15" })).db).toBe(15);
    expect(valkeyOptions(withSecret({})).db).not.toBe(0);
  });

  it("carries the host, port, password and TLS setting, and omits a password and TLS that are not set", () => {
    expect(valkeyOptions(withSecret({}))).toEqual({ host: "localhost", port: 6379, db: 1 });
    expect(
      valkeyOptions(withSecret({ VALKEY_HOST: "valkey", VALKEY_PORT: "6380", VALKEY_PASSWORD: "pw", VALKEY_TLS: "true" })),
    ).toEqual({ host: "valkey", port: 6380, db: 1, password: "pw", tls: {} });
  });
});
