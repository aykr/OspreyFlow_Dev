/**
 * Releases, round 2 of slice IS5a: four things the first round's tests did not press. Each case below presses a control as a
 * browser does, by sending only the fields the form itself would send, so a control that works only beside another is shown.
 *
 *  - the "Check again, replacing my draft" button, pressed on its own, replaces the draft (scripts off has no other way)
 *  - the main "Check the release" button keeps a confirmation already given, as the React screen's `onCheck` does
 *  - every disabled import control carries the rights tip beside it, as the export button does
 *  - a folder with too many files and a session too near its end each say their own words, not the 2 MB words
 *
 * Which test fails if the invariant is broken (rule 12): the first three are the cases named here; the words are the last two.
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

const PAGE = `/studio/releases?case=${CASE_ID}`;
const TOO_LARGE = "That folder is larger than the Studio holds for a check (2 MB).";
const TOO_MANY = "That folder has more files than the Studio holds for a check (200).";

const unescape = (text: string): string =>
  text.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

/** The first `<form>` that holds `needle`, as a browser would submit it when `button` (its text) is pressed. */
function pressed(html: string, button: string, options: { form?: RegExp; ticked?: boolean } = {}): { action: string; fields: Record<string, string> } {
  const forms = [...html.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/g)];
  const form = forms.find((f) => (options.form ? options.form.test(f[1] ?? "") : true) && new RegExp(`>\\s*${button}\\s*</button>`).test(f[2] ?? ""));
  if (!form) throw new Error(`no form has a button "${button}"`);
  const body = form[2] ?? "";
  const fields: Record<string, string> = {};
  for (const input of body.matchAll(/<input\b([^>]*)>/g)) {
    const attrs = input[1] ?? "";
    const name = /\bname="([^"]*)"/.exec(attrs)?.[1];
    const type = /\btype="([^"]*)"/.exec(attrs)?.[1];
    if (name === undefined || /\bdisabled\b/.test(attrs)) continue;
    if (type === "checkbox") {
      // A checkbox is sent only when it is ticked: as it came, or as the person ticked it.
      if (options.ticked ?? /\schecked\b/.test(attrs)) fields[name] = unescape(/\bvalue="([^"]*)"/.exec(attrs)?.[1] ?? "on");
      continue;
    }
    if (type === "file") continue;
    fields[name] = unescape(/\bvalue="([^"]*)"/.exec(attrs)?.[1] ?? "");
  }
  const tag = new RegExp(`<button\\b([^>]*)>\\s*${button}\\s*</button>`).exec(body)?.[1] ?? "";
  const name = /\bname="([^"]*)"/.exec(tag)?.[1];
  if (/\bdisabled\b/.test(tag)) throw new Error(`the button "${button}" is disabled`);
  if (name !== undefined) fields[name] = unescape(/\bvalue="([^"]*)"/.exec(tag)?.[1] ?? "");
  return { action: unescape(/\baction="([^"]*)"/.exec(form[1] ?? "")?.[1] ?? ""), fields };
}

const send = (w: World, step: { action: string; fields: Record<string, string> }) =>
  request(w.app).post(step.action).set("Cookie", w.signed.cookie).type("form").send({ _csrf: w.signed.csrf, ...step.fields });

function multipart(parts: { name: string; value?: string; filename?: string; data?: string }[]): { type: string; body: Buffer } {
  const boundary = `----OspreyRepairs${generateSecret(16)}`;
  const chunks = parts.map((p) => {
    const head =
      p.filename === undefined
        ? `Content-Disposition: form-data; name="${p.name}"\r\n\r\n${p.value ?? ""}`
        : `Content-Disposition: form-data; name="${p.name}"; filename="${p.filename}"\r\nContent-Type: application/octet-stream\r\n\r\n${p.data ?? ""}`;
    return `--${boundary}\r\n${head}\r\n`;
  });
  return { type: `multipart/form-data; boundary=${boundary}`, body: Buffer.from(`${chunks.join("")}--${boundary}--\r\n`) };
}

function uploadFiles(w: World, files: { path: string; data: string }[]) {
  const form = multipart([
    { name: "_csrf", value: w.signed.csrf },
    { name: "case", value: CASE_ID },
    { name: "action", value: "upload" },
    ...files.map((f) => ({ name: "folder", filename: f.path, data: f.data })),
  ]);
  return request(w.app).post("/studio/releases").set("Cookie", w.signed.cookie).set("Content-Type", form.type).send(form.body);
}

const FOLDER = [
  { path: "bundle/release.yaml", data: "apiVersion: ospreyflow.io/v1\n" },
  { path: "bundle/pipelines/visits.yaml", data: "name: visits\n" },
];
const imports = (w: World) => w.conduit.calls.filter((c) => c.path.endsWith("/release/import"));
const importButton = (html: string): string => /<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(html)?.[0] ?? "";

async function firstCheck(w: World): Promise<string> {
  const read = await uploadFiles(w, FOLDER);
  return (await send(w, pressed(read.text, "Check the release"))).text;
}

describe("Releases: replace my draft, pressed as a browser presses it", () => {
  it("the replace button on its own checks again, replacing the draft, with the checkbox never ticked", async () => {
    const w = await make(person({ ownDraft: 3 }));
    const first = await firstCheck(w);
    expect(textOf(first)).toContain("your own in-progress draft");
    expect(importButton(first)).toMatch(/\bdisabled\b/);
    // Exactly what the browser sends for this form when only the button is pressed: the box stays as it came, unticked.
    const step = pressed(first, "Check again, replacing my draft", { form: /id="studio-replace"/, ticked: false });
    expect(step.fields["replace"]).toBeUndefined();
    const second = await send(w, step);
    expect(imports(w).at(-1)?.query.get("dry_run")).toBe("true");
    expect(imports(w).at(-1)?.query.get("replace_own_draft")).toBe("3");
    expect(textOf(second.text)).toContain("Would write Wing phone calls as the draft, in place of the one open now.");
    expect(importButton(second.text)).not.toMatch(/\bdisabled\b/);
    expect(second.text).toMatch(/<input type="checkbox" name="replace" value="1"[^>]* checked/);
  });

  it("the replace button with the box ticked first does the same, once, with no field sent twice", async () => {
    const w = await make(person({ ownDraft: 3 }));
    const first = await firstCheck(w);
    const second = await send(w, pressed(first, "Check again, replacing my draft", { form: /id="studio-replace"/, ticked: true }));
    expect(imports(w).at(-1)?.query.get("replace_own_draft")).toBe("3");
    expect(importButton(second.text)).not.toMatch(/\bdisabled\b/);
  });

  it("after a confirmed check, the main Check button keeps the confirmation, and Import then replaces the draft", async () => {
    const w = await make(person({ ownDraft: 3 }));
    const second = await send(w, pressed(await firstCheck(w), "Check again, replacing my draft", { form: /id="studio-replace"/, ticked: false }));
    const third = await send(w, pressed(second.text, "Check the release", { form: /^(?![^>]*studio-replace)/ }));
    expect(imports(w).at(-1)?.query.get("dry_run")).toBe("true");
    expect(imports(w).at(-1)?.query.get("replace_own_draft")).toBe("3");
    expect(third.text).toMatch(/<input type="checkbox" name="replace" value="1"[^>]* checked/);
    expect(importButton(third.text)).not.toMatch(/\bdisabled\b/);
    await send(w, pressed(third.text, "Import as drafts"));
    expect(imports(w).at(-1)?.query.get("replace_own_draft")).toBe("3");
    expect(w.conduit.written[0]?.replace).toBe("3");
  });

  it("unticking the box and pressing the button takes the confirmation back: no draft is replaced and Import shuts", async () => {
    const w = await make(person({ ownDraft: 3 }));
    const confirmed = await send(w, pressed(await firstCheck(w), "Check again, replacing my draft", { form: /id="studio-replace"/, ticked: false }));
    const again = await send(w, pressed(confirmed.text, "Check again", { form: /id="studio-replace"/, ticked: false }));
    expect(imports(w).at(-1)?.query.has("replace_own_draft")).toBe(false);
    expect(importButton(again.text)).toMatch(/\bdisabled\b/);
    expect(again.text).not.toMatch(/<input type="checkbox" name="replace" value="1"[^>]* checked/);
  });
});

describe("Releases: the rights tip beside every disabled import control", () => {
  it("a person without Edit pipelines sees the tip, and each of the four controls points at it and is disabled", async () => {
    const w = await make(person({ rights: ["edit_target_model", "publish_pipelines"] }));
    const res = await w.get(PAGE);
    expect(res.text).toMatch(/<span id="why-import"[^>]*data-why-not[^>]*>You need Edit pipelines\. Ask an administrator to give it to you\.<\/span>/);
    const controls = [
      /<input\b[^>]*type="file"[^>]*>/.exec(res.text)?.[0],
      /<button\b[^>]*>\s*Read the folder\s*<\/button>/.exec(res.text)?.[0],
      /<button\b[^>]*>\s*Check the release\s*<\/button>/.exec(res.text)?.[0],
      /<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(res.text)?.[0],
    ];
    for (const control of controls) {
      expect(control).toBeDefined();
      expect(control).toMatch(/\bdisabled\b/);
      expect(control).toContain('aria-describedby="why-import"');
    }
    // The export is theirs, so it has no tip.
    expect(res.text).not.toContain('id="why-export"');
    expect(res.text).not.toContain("edit_pipelines");
  });

  it("a person with the rights has no tip and no control pointing at one", async () => {
    const w = await make();
    const res = await w.get(PAGE);
    expect(res.text).not.toContain("why-import");
    expect(res.text).not.toContain("why-export");
  });

  it("a refused upload's page still carries the tip", async () => {
    const w = await make(person({ rights: ["edit_target_model", "publish_pipelines"] }));
    const res = await uploadFiles(w, FOLDER);
    expect(res.status).toBe(403);
    expect(res.text).toContain('id="why-import"');
  });
});

describe("Releases: a refusal says why it refused", () => {
  it("a folder of more than 200 files says it has too many, not that it is too large", async () => {
    const w = await make();
    const files = Array.from({ length: 201 }, (_, i) => ({ path: `bundle/f${i}.yaml`, data: "a: 1\n" }));
    const res = await uploadFiles(w, files);
    expect(res.status).toBe(413);
    expect(textOf(res.text)).toContain(TOO_MANY);
    expect(textOf(res.text)).not.toContain(TOO_LARGE);
    expect(w.store.keys().filter((k) => k.startsWith("pages-staged:"))).toEqual([]);
    // Two hundred is held.
    const ok = await uploadFiles(w, files.slice(0, 200));
    expect(ok.status).toBe(200);
    expect(textOf(ok.text)).toContain("Read 200 files from the folder.");
  });

  it("a folder over 2 MB still says it is too large", async () => {
    const w = await make();
    const res = await uploadFiles(w, [{ path: "bundle/release.yaml", data: "x".repeat(2 * 1024 * 1024 + 1) }]);
    expect(res.status).toBe(413);
    expect(textOf(res.text)).toContain(TOO_LARGE);
    expect(textOf(res.text)).not.toContain(TOO_MANY);
  });

  it("a session too near its end to hold a folder says so, and does not call the folder large", async () => {
    const w = await make(person(), { sessionSeconds: 600 });
    w.clock.advance(599.2);
    const res = await uploadFiles(w, FOLDER);
    const said = textOf(res.text);
    // The session's end is the reason, whether the app notices it before the folder is held or while holding it.
    expect(said).not.toContain(TOO_LARGE);
    expect(said).not.toContain(TOO_MANY);
    expect(res.status).not.toBe(413);
    expect(said).toMatch(/sign(-| )in|session/i);
    expect(w.store.keys().filter((k) => k.startsWith("pages-staged:"))).toEqual([]);
  });
});
