/**
 * The pages server started for the GOV.UK tree against the boards page's fixture Conduit (`boardsConduit.ts`), for the boards page's
 * keyboard and scripts-off specs (slice GG4a; scenario BD14 and BD15). One synthetic case with two boards: one with a drawn item, a loaded
 * one and a drawn link between them, and one with nothing on it. The signed-in person made both, holds a level on the case and the right
 * to investigate.
 */
import type { Page } from "@playwright/test";

import type { Assets } from "./helpServer.js";
import { boardsConduit } from "./boardsConduit.js";
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
  const io = { log: () => undefined, error: () => undefined, exit: () => undefined };
  const running: Running | undefined = await main(
    {
      OSPREY_PAGES_PORT: "0",
      OSPREY_PAGES_SESSION_SECRET: generateSecret(48),
      OSPREY_PAGES_TREE: "govuk",
      OSPREY_PAGES_CONDUIT_URL: conduit.url,
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
    await conduit.stop();
  }
}

export async function openBoards(page: Page, base: string, path = BOARDS_PATH): Promise<void> {
  await page.goto(`${base}/session/sign-in`);
  await page.goto(`${base}${path}`);
}
