/**
 * The pages server started for the GOV.UK tree against the reader page's fixture Conduit (`documentConduit.ts`), for the reader page's
 * keyboard and scripts-off specs (slice GG3b; scenario DR16). One synthetic case of one unit with three documents: a note with marked
 * words, a picture (a real 1x1 PNG, so a browser can be seen to load it through the forwarder under the page's content security
 * policy) and a film. The way back to the case is followed too, so the case's own routes are answered by GR1a's fixture
 * (`casesConduit.ts`): one front server sends a path of a document to the one and every other path to the other, each refusing as the
 * real routes do. The signed-in person holds a level on the case and the right to investigate.
 */
import { createServer, request as httpRequest } from "node:http";
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import type { Page } from "@playwright/test";

import type { Assets } from "./helpServer.js";
import { casesConduit } from "./casesConduit.js";
import { documentConduit } from "./documentConduit.js";
import type { Doc } from "./documentConduit.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { generateSecret } from "../support/secret.js";
import { bearer } from "../support/studioWorld.js";

const UNIT = "keyboard-unit";
export const CASE_ID = "k-harbour";
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");

const doc = (over: Partial<Doc> & Pick<Doc, "id">): Doc => ({
  case_id: CASE_ID,
  title: null,
  text: "",
  truncated: false,
  spans: [],
  sent_at: null,
  sender_id: null,
  recipient_id: null,
  edge_id: null,
  event_id: null,
  media_kind: null,
  has_file: false,
  ...over,
});

export const KEYBOARD_DOCUMENTS: Doc[] = [
  doc({
    id: "k-note",
    title: "Night berth note",
    text: "Ada Quill met the Harbour Board.\nBerth four, after dark.",
    spans: [
      { start: 0, end: 9, node_id: "n-k-1", entity_type: "Person", provenance_state: "asserted" },
      { start: 18, end: 31, node_id: "n-k-2", entity_type: "Organisation", provenance_state: "inferred" },
    ],
  }),
  doc({ id: "k-photo", title: "Gate photograph", media_kind: "image", has_file: true, file: { bytes: PNG, type: "image/png" } }),
  doc({ id: "k-film", title: "Quay camera", media_kind: "video", has_file: true, file: { bytes: Buffer.from("synthetic film"), type: "video/webm" } }),
];

/** The stops of a document's page: the skip link, the layout's sign-out, the way back to the case, the way back to Home. */
export const DOCUMENT_TAB_ORDER = ["a: Skip to main content", "button: Sign out", "a: Back to the case", "a: Back to Home"];
/** A film's page has one stop more, the film's own controls, before the ways back. */
export const FILM_TAB_ORDER = ["a: Skip to main content", "button: Sign out", "video: A film from the document", "a: Back to the case", "a: Back to Home"];

export async function withDocuments(assets: Assets, run: (base: string) => Promise<void>): Promise<void> {
  const token = bearer();
  const reader = { token, unit: UNIT, rights: ["investigate"], levels: { [CASE_ID]: "viewer" as const } };
  const documents = await documentConduit({ readers: [{ ...reader, clearance: 0 }], cases: [{ id: CASE_ID, owning_unit: UNIT }], documents: KEYBOARD_DOCUMENTS });
  const cases = await casesConduit({
    readers: [reader],
    cases: [{ id: CASE_ID, name: "Harbour watch", created_at: "2026-10-02T09:05:00Z", created_by: "acct-k", owning_unit: UNIT, domains: [], datasets: [], brief: { priority: "", requirements: [] } }],
  });
  // One front: a document's path to the reader's fixture, every other path to the cases fixture.
  const front: Server = createServer((req, res) => {
    const target = new URL(/^\/v1\/investigations\/[^/]+\/documents\//.test(req.url ?? "") ? documents.url : cases.url);
    const upstream = httpRequest({ host: target.hostname, port: target.port, path: req.url, method: req.method, headers: req.headers }, (answer) => {
      res.writeHead(answer.statusCode ?? 502, answer.headers);
      answer.pipe(res);
    });
    req.pipe(upstream);
  });
  await new Promise<void>((resolve) => front.listen(0, "127.0.0.1", resolve));
  const io = { log: () => undefined, error: () => undefined, exit: () => undefined };
  const running: Running | undefined = await main(
    {
      OSPREY_PAGES_PORT: "0",
      OSPREY_PAGES_SESSION_SECRET: generateSecret(48),
      OSPREY_PAGES_TREE: "govuk",
      OSPREY_PAGES_CONDUIT_URL: `http://127.0.0.1:${(front.address() as AddressInfo).port}`,
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
    front.closeAllConnections();
    await new Promise<void>((resolve) => front.close(() => resolve()));
    await documents.stop();
    await cases.stop();
  }
}

/**
 * The tab order of a page whose film has controls: a browser gives `<video controls>` several stops of its own (play, the timeline,
 * the sound, full screen), each reported as the video, so `tabOrder`'s stop at the first name seen twice would end the walk inside the
 * film. This walk counts a run of stops on one element as one, and goes on until focus leaves the page or comes back to a stop already
 * passed, so it proves the keyboard gets past the film to what follows it (no trap).
 */
export async function tabOrderPastControls(page: Page): Promise<string[]> {
  const seen: string[] = [];
  for (let i = 0; i < 60; i += 1) {
    await page.keyboard.press("Tab");
    const name = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return "(page)";
      const label = el.getAttribute("aria-label") ?? el.textContent ?? "";
      return `${el.tagName.toLowerCase()}: ${label.replace(/\s+/g, " ").trim()}`;
    });
    if (name === "(page)") break;
    if (seen[seen.length - 1] === name) continue;
    if (seen.includes(name)) break;
    seen.push(name);
  }
  return seen;
}

export const documentPath = (id: string): string => `/cases/document?case=${CASE_ID}&document=${id}`;

export async function openDocument(page: Page, base: string, id: string): Promise<void> {
  await page.goto(`${base}/session/sign-in`);
  await page.goto(`${base}${documentPath(id)}`);
}
