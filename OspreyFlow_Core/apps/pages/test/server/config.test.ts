/** The service's own database number: not the Conduit's, which holds its working sets in db 0. */
import { describe, expect, it } from "vitest";

import { loadConfig } from "../../server/config.js";

describe("loadConfig", () => {
  it("defaults to port 8090 and Valkey database 1", () => {
    const config = loadConfig({});
    expect(config.port).toBe(8090);
    expect(config.valkey.db).toBe(1);
    expect(config.valkey.host).toBe("localhost");
    expect(config.valkey.port).toBe(6379);
  });

  it("takes the database number from OSPREY_PAGES_VALKEY_DB", () => {
    expect(loadConfig({ OSPREY_PAGES_VALKEY_DB: "4" }).valkey.db).toBe(4);
  });

  it.each(["0", "-1", "abc", "1.5", "", "99999"])("refuses %j as the database number", (value) => {
    expect(() => loadConfig({ OSPREY_PAGES_VALKEY_DB: value })).toThrow(/OSPREY_PAGES_VALKEY_DB/);
  });

  it("refuses the Conduit's own database, wherever the Conduit has been told to put it", () => {
    expect(() => loadConfig({ VALKEY_DB: "1" })).toThrow(/Conduit/);
    expect(() => loadConfig({ VALKEY_DB: "3", OSPREY_PAGES_VALKEY_DB: "3" })).toThrow(/Conduit/);
    expect(loadConfig({ VALKEY_DB: "0", OSPREY_PAGES_VALKEY_DB: "1" }).valkey.db).toBe(1);
  });

  it("reads the Conduit's Valkey settings, by the Conduit's own names", () => {
    const config = loadConfig({ VALKEY_HOST: "valkey", VALKEY_PORT: "6380", VALKEY_PASSWORD: "pw", VALKEY_TLS: "true" });
    expect(config.valkey).toMatchObject({ host: "valkey", port: 6380, password: "pw", tls: true });
  });
});
