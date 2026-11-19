/** The service's own database number: not the Conduit's, which holds its working sets in db 0. */
import { format, inspect } from "node:util";

import { describe, expect, it } from "vitest";

import { loadConfig } from "../../server/config.js";
import { valkeyOptions } from "../../server/valkey.js";
import { captureOutput } from "../support/capture.js";
import { generateSecret } from "../support/secret.js";

/** Made now, at run time, and written nowhere. */
const SECRET = generateSecret();

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
    expect(loadConfig({ OSPREY_PAGES_SESSION_SECRET: SECRET }).sessionSecret.reveal()).toBe(SECRET);
  });

  it("is required: no secret, no service", () => {
    expect(() => loadConfig({})).toThrow(/OSPREY_PAGES_SESSION_SECRET/);
    expect(() => loadConfig({ OSPREY_PAGES_SESSION_SECRET: "" })).toThrow(/OSPREY_PAGES_SESSION_SECRET/);
  });

  it("is at least 32 characters: 31 is refused and 32 is accepted", () => {
    expect(() => loadConfig({ OSPREY_PAGES_SESSION_SECRET: generateSecret(31) })).toThrow(/at least 32/);
    expect(loadConfig({ OSPREY_PAGES_SESSION_SECRET: generateSecret(32) }).sessionSecret.reveal()).toHaveLength(32);
  });

  it("is never in a message that refuses something else, or in one that refuses it", () => {
    const short = generateSecret(21);
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

describe("the configuration's own printed and JSON forms show the secret as redacted", () => {
  const secret = generateSecret();
  const config = loadConfig({ OSPREY_PAGES_SESSION_SECRET: secret, VALKEY_HOST: "valkey" });

  const forms = (): Record<string, string> => ({
    "JSON.stringify": JSON.stringify(config),
    "JSON.stringify, indented": JSON.stringify(config, null, 2),
    "JSON.stringify of a spread copy": JSON.stringify({ ...config }),
    "String": String(config.sessionSecret),
    "a template literal": `${config.sessionSecret}`,
    "util.inspect": inspect(config, { depth: null, showHidden: true }),
    "util.inspect of the secret alone": inspect(config.sessionSecret, { showHidden: true }),
    "util.format": format("%s %o %j", config.sessionSecret, config, config),
    "Object.values": JSON.stringify(Object.values(config.sessionSecret)),
    "Object.getOwnPropertyNames": Object.getOwnPropertyNames(config.sessionSecret).join(","),
  });

  it.each(Object.keys(forms()))("holds none of it in %s", (form) => {
    const text = forms()[form] as string;
    expect(text).not.toContain(secret);
    expect(text).not.toContain(Buffer.from(secret).toString("base64"));
  });

  it("says redacted in its JSON form, and keeps the other settings readable", () => {
    const parsed = JSON.parse(JSON.stringify(config)) as { sessionSecret: unknown; valkey: { host: string }; port: number };
    expect(parsed.sessionSecret).toBe("[redacted]");
    expect(parsed.valkey.host).toBe("valkey");
    expect(parsed.port).toBe(8090);
  });

  it("is not in the console when the configuration is logged, however the logging is done", () => {
    const captured = captureOutput();
    try {
      console.log(config);
      console.error("config:", config);
      console.info(`${JSON.stringify(config)}`);
      process.stdout.write(inspect(config) + "\n");
    } finally {
      captured.restore();
    }
    expect(captured.text()).toContain("[redacted]");
    expect(captured.text()).not.toContain(secret);
  });

  it("can still be used: revealing it is a deliberate call, and it yields the value given", () => {
    expect(config.sessionSecret.reveal()).toBe(secret);
  });
});
