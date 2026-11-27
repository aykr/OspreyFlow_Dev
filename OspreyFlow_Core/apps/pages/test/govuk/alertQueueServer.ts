/**
 * What the alert queue's Playwright case shares (slice RM1a): the pages service started for the `govuk` tree with the fixture Conduit's
 * address (`alertQueueConduit.ts`, which refuses what the real queue route refuses), signing in as one of the fixture's readers, on a free
 * port, with the real assets built to a scratch folder and the in-memory store. Everything else (the front proxy's word that the request
 * came over TLS, the tab order read off the page) is `helpServer.ts`'s.
 */
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { noSessionEvents } from "../support/noSessionEvents.js";
import { generateSecret } from "../support/secret.js";
import type { Reader } from "./alertQueueConduit.js";
import type { Assets, Govuk } from "./helpServer.js";

export async function startQueueService(assets: Assets, conduitUrl: string, reader: Reader): Promise<Govuk> {
  const said: string[] = [];
  const io = { log: () => undefined, error: (message: string) => void said.push(message), exit: () => undefined };
  const running: Running | undefined = await main(
    {
      OSPREY_PAGES_PORT: "0",
      OSPREY_PAGES_SESSION_SECRET: generateSecret(48),
      OSPREY_PAGES_TREE: "govuk",
      OSPREY_PAGES_CONDUIT_URL: conduitUrl,
      // Required with a Conduit address (the live-updates proxy compares an upgrade's origin with it): the page makes no upgrade.
      OSPREY_PAGES_PUBLIC_ORIGIN: "https://pages.example.org",
    },
    io,
    {
      store: new MemorySessionStore(),
      host: "127.0.0.1",
      assets,
      sessionEvents: noSessionEvents,
      identityProvider: {
        async signIn() {
          return {
            subject: "sub-queue-keyboard",
            displayName: "Alex Example",
            accessToken: reader.token,
            refreshToken: "not-used",
            idpSessionExpiresAt: Date.now() + 3_600_000,
          };
        },
      },
    },
  );
  if (!running) throw new Error(`the pages server did not start: ${said.join(" ")}`);
  return { base: `http://127.0.0.1:${running.port}`, stop: () => running.stop() };
}
