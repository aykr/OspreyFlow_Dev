/**
 * The pages server started for the GOV.UK tree against the boards page's fixture Conduit (`boardsConduit.ts`), for the boards page's
 * keyboard and scripts-off specs (slice GG4a; scenario BD14 and BD15). One synthetic case with two boards: one with a drawn item, a loaded
 * one and a drawn link between them, and one with nothing on it. The signed-in person made both, holds a level on the case and the right
 * to investigate. The case's own routes are the cases page's fixture's (`casesConduit.ts`), so the way back to the case lands on its real
 * page: one address in front of both fixtures sends each request to the one that models its route, unchanged.
 */
import { request as forward, createServer } from "node:http";
import type { AddressInfo } from "node:net";

import type { Page } from "@playwright/test";

import type { Assets } from "./helpServer.js";
import { boardsConduit } from "./boardsConduit.js";
import { casesConduit } from "./casesConduit.js";
import type { Board, Item, Link } from "./boardsConduit.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { generateSecret } from "../support/secret.js";
import { bearer } from "../support/studioWorld.js";

const UNIT = "keyboard-unit";
const ME = "acct-k";
const CASE = "k-harbour";
const assertion = (item: string, label: string): NonNullable<Item["drawn"]> => ({
  label,
  grading: { scheme: "5x5x5", source: "B", intelligence: "2", handling: "1" },
  source_note: "Seen from the quay",
  source_document: null,
  asserted_by: ME,
  item_id: item,
  board_id: "k-quay",
});
const ITEMS: Item[] = [
  { id: "k-vessel", type: "Vessel", properties: { name: "Evening Tide" }, marking: "OFFICIAL" },
  { id: "k-tall", type: "Person", properties: {}, marking: "OFFICIAL", drawn: assertion("i-k-tall", "Tall man") },
];
const LINKS: Link[] = [{ id: "k-boards", type: "BOARDS", source: "k-tall", target: "k-vessel", marking: "OFFICIAL", drawn: assertion("i-k-boards", "Boards at night") }];
const BOARDS: Board[] = [
  { id: "k-quay", case_id: CASE, name: "Quay sketch", created_by: ME, created_at: "2026-11-10T09:30:00Z", shared: true, references: ["k-vessel"], drawn: ["k-tall"] },
  { id: "k-empty", case_id: CASE, name: "Empty start", created_by: ME, created_at: "2026-11-11T09:30:00Z", shared: false, references: [], drawn: [] },
];

export const BOARDS_PATH = `/cases/boards?case=${CASE}`;
export const QUAY_PATH = `/cases/boards?case=${CASE}&board=k-quay`;
/** The stops of the list, in the page's own order: the skip link, the layout's sign-out, each board's link, the ways back. */
export const LIST_TAB_ORDER = ["a: Skip to main content", "button: Sign out", "a: Quay sketch", "a: Empty start", "a: Back to this case", "a: Back to Home"];
/** The stops of a board: the skip link, the sign-out, the way back to the case's boards, the way back to Home; the tables add none. */
export const BOARD_TAB_ORDER = ["a: Skip to main content", "button: Sign out", "a: Back to this case's boards", "a: Back to Home"];

export async function withBoards(assets: Assets, run: (base: string) => Promise<void>): Promise<void> {
  const token = bearer();
  const conduit = await boardsConduit({
    readers: [{ token, id: ME, unit: UNIT, rights: ["investigate"], cases: [CASE], clearance: "OFFICIAL" }],
    cases: [{ id: CASE, owning_unit: UNIT }],
    boards: BOARDS,
    items: ITEMS,
    links: LINKS,
  });
  const cases = await casesConduit({
    readers: [{ token, unit: UNIT, rights: ["investigate"], levels: { [CASE]: "author" } }],
    cases: [{ id: CASE, name: "Harbour watch", created_at: "2026-10-02T09:05:00Z", created_by: ME, owning_unit: UNIT, domains: [], datasets: [], brief: { priority: "", requirements: [] } }],
  });
  // Each request to whichever fixture models its route: the boards' routes to the boards fixture, every other to the cases fixture.
  const front = createServer((req, res) => {
    const target = new URL(/^\/v1\/investigations\/[^/]+\/boards(?:\/|$|\?)/.test(req.url ?? "") ? conduit.url : cases.url);
    const onward = forward({ host: target.hostname, port: target.port, path: req.url, method: req.method, headers: req.headers }, (answer) => {
      res.writeHead(answer.statusCode ?? 502, answer.headers);
      answer.pipe(res);
    });
    req.pipe(onward);
  });
  await new Promise<void>((resolve) => front.listen(0, "127.0.0.1", resolve));
  const frontUrl = `http://127.0.0.1:${(front.address() as AddressInfo).port}`;
  const io = { log: () => undefined, error: () => undefined, exit: () => undefined };
  const running: Running | undefined = await main(
    {
      OSPREY_PAGES_PORT: "0",
      OSPREY_PAGES_SESSION_SECRET: generateSecret(48),
      OSPREY_PAGES_TREE: "govuk",
      OSPREY_PAGES_CONDUIT_URL: frontUrl,
      OSPREY_PAGES_PUBLIC_ORIGIN: "https://osprey.test",
    },
    io,
    {
      store: new MemorySessionStore(),
      host: "127.0.0.1",
      assets,
      identityProvider: {
        async signIn() {
          return { subject: "sub-keyboard", displayName: "Alex Example", accessToken: token, refreshToken: "not-used", idpSessionExpiresAt: Date.now() + 3_600_000 };
        },
      },
    },
  );
  if (!running) throw new Error("the pages server did not start");
  try {
    await run(`http://127.0.0.1:${running.port}`);
  } finally {
    await running.stop();
    await new Promise<void>((resolve) => front.close(() => resolve()));
    await cases.stop();
    await conduit.stop();
  }
}

export async function openBoards(page: Page, base: string, path = BOARDS_PATH): Promise<void> {
  await page.goto(`${base}/session/sign-in`);
  await page.goto(`${base}${path}`);
}
