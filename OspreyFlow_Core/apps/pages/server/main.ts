/** The pages service's entry point: Valkey for sessions, no identity provider until the real exchange is built. */
import { Redis } from "ioredis";

import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { unconfiguredProvider } from "./identity.js";
import { ValkeySessionStore } from "./sessionStore.js";
import { valkeyOptions } from "./valkey.js";

const config = loadConfig();
const client = new Redis(valkeyOptions(config));
client.on("error", (error: Error) => {
  console.error("pages: valkey:", error.message);
});

const app = createApp({
  store: new ValkeySessionStore(client),
  identityProvider: unconfiguredProvider,
  sessionSecret: config.sessionSecret,
});
const server = app.listen(config.port, "0.0.0.0", () => {
  console.log(`pages: listening on ${config.port}`);
});

function stop(): void {
  server.close(() => {
    client.disconnect();
    process.exit(0);
  });
}
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
