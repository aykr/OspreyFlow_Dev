/** The pages service's entry point: Valkey for sessions, no identity provider until the real exchange is built. */
import { main } from "./start.js";

const running = await main();

if (running) {
  const stop = (): void => {
    void running.stop().then(() => process.exit(0));
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}
