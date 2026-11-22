/**
 * The Releases page's upload reader, from the browser's side (slice IS5a): what a form that is not proven is never allowed to
 * do. Complements `studio-releases.test.ts` SR12, whose forms always carry fields: these are the forms an attacker would send,
 * a file with no fields at all, and a proof that arrives after a file. Each shows the layer that refuses it (rule 15: the same
 * cases were run with that layer removed, and red).
 */
import { afterEach, describe, expect, it } from "vitest";

import { request } from "../support/http.js";
import { CASE_ID, world } from "../support/studioWorld.js";
import type { World } from "../support/studioWorld.js";

const open: World[] = [];
afterEach(async () => {
  while (open.length > 0) await open.pop()?.stop();
});

function body(parts: string[]): { type: string; payload: Buffer } {
  const boundary = "----OspreyUploadTest";
  const text = parts.map((part) => `--${boundary}\r\n${part}\r\n`).join("") + `--${boundary}--\r\n`;
  return { type: `multipart/form-data; boundary=${boundary}`, payload: Buffer.from(text) };
}

const field = (name: string, value: string): string => `Content-Disposition: form-data; name="${name}"\r\n\r\n${value}`;
const file = (name: string, filename: string, text: string): string =>
  `Content-Disposition: form-data; name="${name}"; filename="${filename}"\r\nContent-Type: application/octet-stream\r\n\r\n${text}`;

async function post(w: World, parts: string[]) {
  const form = body(parts);
  return request(w.app).post("/studio/releases").set("Cookie", w.signed.cookie).set("Content-Type", form.type).send(form.payload);
}

describe("an upload that is not proven", () => {
  it("a form of nothing but a file is refused, with nothing asked of the Conduit and nothing held", async () => {
    const w = await world();
    open.push(w);
    const res = await post(w, [file("folder", "bundle/release.yaml", "apiVersion: ospreyflow.io/v1\n")]);
    expect(res.status).toBe(403);
    // Refused for the missing proof, in the general words, not for some other reason that also happens to be a 403.
    expect(res.text).toContain("This request could not be checked, so it was not carried out.");
    expect(res.text).not.toContain("Read 1 file");
    expect(w.conduit.calls).toEqual([]);
    expect(w.store.keys().filter((k) => k.startsWith("pages-staged:"))).toEqual([]);
  });

  it("a proof that arrives after a field or a file is no proof, and the Conduit is not asked", async () => {
    const w = await world();
    open.push(w);
    for (const parts of [
      [field("case", CASE_ID), field("_csrf", w.signed.csrf), file("folder", "b/release.yaml", "x")],
      [file("folder", "b/release.yaml", "x"), field("_csrf", w.signed.csrf)],
      [field("_csrf", "not-the-token"), field("case", CASE_ID), file("folder", "b/release.yaml", "x")],
    ]) {
      const res = await post(w, parts);
      expect(res.status).toBe(403);
      expect(res.text).toContain("This request could not be checked, so it was not carried out.");
    }
    expect(w.conduit.calls).toEqual([]);
    expect(w.store.keys().filter((k) => k.startsWith("pages-staged:"))).toEqual([]);
  });

  it("a proven form with no file reads as no folder chosen, and one with its fields after the file is refused", async () => {
    const w = await world();
    open.push(w);
    const none = await post(w, [field("_csrf", w.signed.csrf), field("case", CASE_ID), field("action", "upload")]);
    expect(none.status).toBe(200);
    expect(none.text).toContain("Choose the release&#39;s folder first.");
    const late = await post(w, [
      field("_csrf", w.signed.csrf),
      field("case", CASE_ID),
      file("folder", "b/release.yaml", "x"),
      field("action", "upload"),
    ]);
    expect(late.status).toBe(422);
    expect(w.store.keys().filter((k) => k.startsWith("pages-staged:"))).toEqual([]);
  });

  it("a form with no boundary cannot be read, and does nothing", async () => {
    const w = await world();
    open.push(w);
    const res = await request(w.app)
      .post("/studio/releases")
      .set("Cookie", w.signed.cookie)
      .set("Content-Type", "multipart/form-data")
      .send("nothing");
    expect(res.status).toBe(422);
    expect(res.text).toContain("The form could not be read. Go back and send it again.");
    expect(w.conduit.calls).toEqual([]);
  });
});
