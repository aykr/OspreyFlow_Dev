/**
 * Releases, round 3 of slice IS5a: the Conduit's own refusal words reach the person, and a permanent refusal is never worded as
 * a passing fault. The fake Conduit gives the 409s and 422s the real routes give (`composite_read_only`, `drawn_not_loaded`,
 * FastAPI's length limits on the export's name and version), so a page that hides them is seen (rule 15).
 *
 * Which test fails if the invariant is broken (rule 12): a 4xx the Conduit explains in a string `detail` is shown as said, but a
 * 401, 403 or 404 never is (rule 3: the same words for "no such dataset" and "not allowed"); a 5xx says to try again, a 4xx never does.
 *  - the import into a composite, and into a drawn dataset, each say the Conduit's words, and do not say "try again" -> RR1, RR2
 *  - the same as the import's check, then the write                                                                  -> RR3
 *  - the export's 422 for a name over 253 characters or a version over 64 says it was refused, not "try again"        -> RR4
 *  - a 403 and a 404 still never show the Conduit's detail, which can name a right                                    -> RR5
 *  - a failing Conduit (500) still says to try again                                                                  -> RR6
 */
import { afterEach, describe, expect, it } from "vitest";

import { request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { COMPOSITE_WORDS, DRAWN_WORDS } from "../support/fakeConduit.js";
import { CASE_ID, caseRow, person, textOf, world } from "../support/studioWorld.js";
import type { World } from "../support/studioWorld.js";
import { refusalWords } from "../../server/views/studioWords.js";

const open: World[] = [];
async function make(...args: Parameters<typeof world>): Promise<World> {
  const w = await world(...args);
  open.push(w);
  return w;
}
afterEach(async () => {
  while (open.length > 0) await open.pop()?.stop();
});

const PAGE = `/studio/releases?case=${CASE_ID}`;
const TRY_AGAIN = /Try again in a few minutes/;

async function uploaded(w: World): Promise<string> {
  const boundary = `----OspreyRefusals${generateSecret(16)}`;
  const part = (name: string, value: string): string => `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`;
  const file = `--${boundary}\r\nContent-Disposition: form-data; name="folder"; filename="bundle/release.yaml"\r\nContent-Type: application/octet-stream\r\n\r\napiVersion: ospreyflow.io/v1\r\n`;
  const body = `${part("_csrf", w.signed.csrf)}${part("case", CASE_ID)}${part("action", "upload")}${file}--${boundary}--\r\n`;
  const res = await request(w.app)
    .post("/studio/releases")
    .set("Cookie", w.signed.cookie)
    .set("Content-Type", `multipart/form-data; boundary=${boundary}`)
    .send(Buffer.from(body));
  return /name="staged" value="([^"]+)"/.exec(res.text)?.[1] ?? "";
}

describe("Releases: the Conduit's own words for a refusal that will not pass", () => {
  it.each([
    ["composite", COMPOSITE_WORDS],
    ["drawn", DRAWN_WORDS],
  ] as const)("RR1/RR2: a %s dataset's import refusal is said in the Conduit's words, with no 'try again'", async (kind, words) => {
    const w = await make(person({ datasetKind: kind, cases: [caseRow()] }));
    const token = await uploaded(w);
    expect(token).not.toBe("");
    const res = await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "check" });
    expect(res.text).toMatch(/<p role="alert">[^<]+<\/p>/);
    expect(textOf(res.text)).toContain(words);
    expect(textOf(res.text)).not.toMatch(TRY_AGAIN);
    expect(w.conduit.calls.filter((c) => c.path.endsWith("/release/import"))).toHaveLength(1);
  });

  it("RR3: a write refused for a composite (made one since the check) says the same words, and nothing is marked written", async () => {
    const w = await make();
    const token = await uploaded(w);
    expect((await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "check" })).status).toBe(200);
    w.me.datasetKind = "composite";
    const res = await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import" });
    expect(textOf(res.text)).toContain(COMPOSITE_WORDS);
    expect(textOf(res.text)).not.toMatch(TRY_AGAIN);
    expect(w.conduit.written).toEqual([]);
  });

  it("RR4: an export name over 253 characters, or a version over 64, is said to be refused, never as a fault to try again", async () => {
    const w = await make();
    for (const query of [`name=${"a".repeat(254)}&version=1`, `name=wing&version=${"1".repeat(65)}`]) {
      const res = await w.get(`${PAGE}&${query}&export=1`);
      expect(textOf(res.text)).toMatch(/The export was refused \(422\)\./);
      expect(textOf(res.text)).not.toMatch(TRY_AGAIN);
    }
  });

  it("RR5: a 403 and a 404 still never show the Conduit's own detail, which can name a right", () => {
    const detail = "Missing right: edit_target_model, edit_pipelines";
    const forbidden = refusalWords(403, { detail }, "The import");
    const absent = refusalWords(404, { detail: "Not Found" }, "The import");
    expect(forbidden).toBe(absent);
    expect(forbidden).not.toContain("edit_");
    expect(refusalWords(401, { detail: "Not authenticated" }, "The import")).toMatch(/Sign in again/);
    // Even a 409 that came with a detail naming a right is shown only as a 4xx's words, never for 401, 403, 404.
    expect(refusalWords(409, { detail: "words" }, "The import")).toBe("words");
  });

  it("RR6: a Conduit that fails (500) or cannot be reached still says nothing was changed and to try again", () => {
    for (const status of [500, 502, 503]) {
      expect(refusalWords(status, { detail: "Internal Server Error" }, "The import")).toMatch(TRY_AGAIN);
    }
    expect(refusalWords(502, undefined, "The export")).toMatch(TRY_AGAIN);
    // A 4xx with no words to give is still not a passing fault.
    expect(refusalWords(409, undefined, "The import")).toBe("The import was refused (409).");
  });
});
