/**
 * Releases, round 4 of slice IS5a: three things the verifier found.
 *
 *  - the held folder is never written to disk. The deployment's Valkey saves its keys to disk (it runs with its built-in save
 *    points), so a folder is held in the pages process's own memory and never reaches the session store; the Valkey store
 *    refuses the folder's key as a second guard.
 *  - a session that ends between the Conduit's dry run and the writing down of its result says so in words (the same words as
 *    one that ends while the folder is read), for a clean check and for a refused write alike; it is not a 500.
 *
 * Which test fails if the invariant is broken (rule 12): the first case is the disk claim, through the route; the Valkey
 * refusal is `test/server/studioStaging.test.ts`'s; the last two are the session's end after the check and after a refused write.
 */
import { afterEach, describe, expect, it } from "vitest";

import { request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { CASE_ID, person, textOf, world } from "../support/studioWorld.js";
import type { World, WorldOptions } from "../support/studioWorld.js";

const open: World[] = [];
async function make(me?: Parameters<typeof world>[0], options?: WorldOptions): Promise<World> {
  const w = await world(me, [], options);
  open.push(w);
  return w;
}
afterEach(async () => {
  while (open.length > 0) await open.pop()?.stop();
});

const unescape = (text: string): string =>
  text.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

/** The form that holds `button`, as a browser would submit it when that button is pressed. */
function pressed(html: string, button: string): { action: string; fields: Record<string, string> } {
  const forms = [...html.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/g)];
  const form = forms.find((f) => new RegExp(`>\\s*${button}\\s*</button>`).test(f[2] ?? ""));
  if (!form) throw new Error(`no form has a button "${button}"`);
  const body = form[2] ?? "";
  const fields: Record<string, string> = {};
  for (const input of body.matchAll(/<input\b([^>]*)>/g)) {
    const attrs = input[1] ?? "";
    const name = /\bname="([^"]*)"/.exec(attrs)?.[1];
    const type = /\btype="([^"]*)"/.exec(attrs)?.[1];
    if (name === undefined || /\bdisabled\b/.test(attrs) || type === "file" || type === "checkbox") continue;
    fields[name] = unescape(/\bvalue="([^"]*)"/.exec(attrs)?.[1] ?? "");
  }
  const tag = new RegExp(`<button\\b([^>]*)>\\s*${button}\\s*</button>`).exec(body)?.[1] ?? "";
  const name = /\bname="([^"]*)"/.exec(tag)?.[1];
  if (name !== undefined) fields[name] = unescape(/\bvalue="([^"]*)"/.exec(tag)?.[1] ?? "");
  return { action: unescape(/\baction="([^"]*)"/.exec(form[1] ?? "")?.[1] ?? ""), fields };
}

const send = (w: World, step: { action: string; fields: Record<string, string> }) =>
  request(w.app).post(step.action).set("Cookie", w.signed.cookie).type("form").send({ _csrf: w.signed.csrf, ...step.fields });

function uploadFiles(w: World, files: { path: string; data: string }[]) {
  const boundary = `----OspreyRound4${generateSecret(16)}`;
  const parts = [
    `Content-Disposition: form-data; name="_csrf"\r\n\r\n${w.signed.csrf}`,
    `Content-Disposition: form-data; name="case"\r\n\r\n${CASE_ID}`,
    `Content-Disposition: form-data; name="action"\r\n\r\nupload`,
    ...files.map((f) => `Content-Disposition: form-data; name="folder"; filename="${f.path}"\r\nContent-Type: application/octet-stream\r\n\r\n${f.data}`),
  ];
  const body = Buffer.from(`${parts.map((p) => `--${boundary}\r\n${p}\r\n`).join("")}--${boundary}--\r\n`);
  return request(w.app).post("/studio/releases").set("Cookie", w.signed.cookie).set("Content-Type", `multipart/form-data; boundary=${boundary}`).send(body);
}

const FOLDER = [
  { path: "bundle/release.yaml", data: "apiVersion: ospreyflow.io/v1\n" },
  { path: "bundle/pipelines/visits.yaml", data: "name: visits\n" },
];
const ENDING = "Your sign-in is about to end, so the folder could not be held. Sign in again and choose the folder again.";

/** Moves the clock to just before the session's end when the Conduit is asked for an import of the given kind. */
function endSessionAt(w: World, dryRun: "true" | "false"): { fired: () => boolean } {
  const push = w.conduit.calls.push.bind(w.conduit.calls);
  let fired = false;
  w.conduit.calls.push = (...seen) => {
    const call = seen[0];
    if (!fired && call !== undefined && call.path.endsWith("/release/import") && call.query.get("dry_run") === dryRun) {
      fired = true;
      w.clock.advance(599.2);
    }
    return push(...seen);
  };
  return { fired: () => fired };
}

describe("Releases: the held folder is never written to disk", () => {
  it("a folder uploaded, checked and imported reaches the session store under no key of its own, and the steps still work", async () => {
    const writes: string[] = [];
    const w = await make(person(), { sessionStoreWrites: writes });
    const read = await uploadFiles(w, FOLDER);
    expect(textOf(read.text)).toContain("Read 2 files from the folder.");
    const checked = await send(w, pressed(read.text, "Check the release"));
    expect(textOf(checked.text)).toContain("Would write");
    const done = await send(w, pressed(checked.text, "Import as drafts"));
    expect(textOf(done.text)).toContain("Wrote");
    expect(w.conduit.written).toHaveLength(1);
    // The session itself was written (so the recorder works); the folder was not.
    expect(writes.some((key) => key.startsWith("pages-session:"))).toBe(true);
    expect(writes.filter((key) => key.startsWith("pages-staged:"))).toEqual([]);
  });
});

describe("Releases: a session that ends after the Conduit has answered", () => {
  it("after a check says so in words, not as a fault", async () => {
    const w = await make(person(), { sessionSeconds: 600 });
    const read = await uploadFiles(w, FOLDER);
    const end = endSessionAt(w, "true");
    const res = await send(w, pressed(read.text, "Check the release"));
    expect(end.fired()).toBe(true);
    expect(res.status).toBe(503);
    expect(textOf(res.text)).toContain(ENDING);
    expect(textOf(res.text)).not.toContain("Something went wrong on our side");
    expect(w.logs.join("\n")).not.toContain("unhandled");
  });

  it("after a write the Conduit refused says so in words, not as a fault", async () => {
    const w = await make(person(), { sessionSeconds: 600 });
    const read = await uploadFiles(w, FOLDER);
    const checked = await send(w, pressed(read.text, "Check the release"));
    expect(textOf(checked.text)).toContain("Would write");
    w.conduit.refuseNextWrite = ["the domain model has your own in-progress draft (version 4): importing replaces it"];
    const end = endSessionAt(w, "false");
    const res = await send(w, pressed(checked.text, "Import as drafts"));
    expect(end.fired()).toBe(true);
    expect(res.status).toBe(503);
    expect(textOf(res.text)).toContain(ENDING);
    expect(textOf(res.text)).not.toContain("Something went wrong on our side");
    expect(w.logs.join("\n")).not.toContain("unhandled");
  });
});
