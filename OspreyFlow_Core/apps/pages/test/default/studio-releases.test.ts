/**
 * Studio › Releases as a server-rendered page, Default tree (slice IS5a; ADR-140 Amendment 9 decision 4; ADR-152
 * decisions 5, 7 and 12; FUNCTIONS row `studio-releases`). Written against today's React screen
 * (`apps/workspace/src/ingest/releases/ReleasesTab.tsx`, its twelve vitest cases and the three keyboard cases): each case's
 * id is a scenario of `spec/08_ACCEPTANCE_SCENARIOS.md` ("Scenario S"), and
 * `tests/glass_trees/test_studio_frame_scenarios.py` holds the two in step.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - an export or an import offered to, or carried out for, someone without its rights  -> SR4, SR11
 *  - an import before a clean check, or after a refused one                            -> SR8
 *  - the import's words saying a model went live                                       -> SR8, SR16
 *  - a folder's own name kept in the paths sent                                        -> SR6
 *  - a draft of the importer's own replaced without the version the check named        -> SR9
 *  - a POST that is not anti-forgery checked, an upload whose token is not first       -> SR12
 *  - a staged bundle that outlives its session, is read by another, or is never removed-> SR13
 *  - the bundle in a log line, an address, a cookie, a page or its data block          -> SR15 (with the checker shown red
 *    against each planted fault, rule 15, in the shape the code would emit it)
 *  - "no such dataset" and "not allowed" told apart                                    -> SR3
 */
import { afterEach, describe, expect, it } from "vitest";

import { captureOutput } from "../support/capture.js";
import { request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { EXPORT_FILES } from "../support/fakeConduit.js";
import { CASE_ID, DATASET, caseRow, findLeaks, person, textOf, world } from "../support/studioWorld.js";
import type { Observations, World } from "../support/studioWorld.js";

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
const MARKER = `BUNDLE-MARKER-${generateSecret(12)}`;
const DRAFTS = "Everything imported is a draft. Make the model live in 1 Model when it is ready.";
const REFUSED_BODY = (what: string): string => `${what} is not available to you: it needs rights you do not hold, or the dataset is not one of yours.`;

interface Part {
  path: string;
  text: string;
}
const FOLDER: Part[] = [
  { path: "bundle/release.yaml", text: `apiVersion: ospreyflow.io/v1\n# ${MARKER}\n` },
  { path: "bundle/pipelines/visits.yaml", text: "name: visits\n" },
];

type FormPart = { name: string; value: string } | { name: string; filename: string; data: Buffer };

/** A multipart body written by hand, as a browser writes it: each part in the order given, a file's name as the browser sends it. */
function multipart(parts: FormPart[]): { type: string; body: Buffer } {
  const boundary = `----OspreyTest${generateSecret(16)}`;
  const chunks: Buffer[] = [];
  for (const part of parts) {
    const head =
      "filename" in part
        ? `Content-Disposition: form-data; name="${part.name}"; filename="${part.filename}"\r\nContent-Type: application/octet-stream\r\n\r\n`
        : `Content-Disposition: form-data; name="${part.name}"\r\n\r\n`;
    chunks.push(Buffer.from(`--${boundary}\r\n${head}`), "filename" in part ? part.data : Buffer.from(part.value), Buffer.from("\r\n"));
  }
  chunks.push(Buffer.from(`--${boundary}--\r\n`));
  return { type: `multipart/form-data; boundary=${boundary}`, body: Buffer.concat(chunks) };
}

/** A browser's folder upload with scripts off: the token first, then the fields, then a file part per file named by its path. */
function upload(w: World, parts: Part[] = FOLDER, options: { csrf?: string | false; tokenFirst?: boolean; session?: string } = {}) {
  const token = options.csrf === undefined ? w.signed.csrf : options.csrf;
  const fields: FormPart[] = [
    { name: "case", value: CASE_ID },
    { name: "action", value: "upload" },
  ];
  const proof: FormPart[] = token === false ? [] : [{ name: "_csrf", value: token }];
  const files: FormPart[] = parts.map((p) => ({ name: "folder", filename: p.path, data: Buffer.from(p.text) }));
  const form = multipart(options.tokenFirst === false ? [...fields, ...proof, ...files] : [...proof, ...fields, ...files]);
  return request(w.app)
    .post("/studio/releases")
    .set("Cookie", options.session ?? w.signed.cookie)
    .set("Content-Type", form.type)
    .send(form.body);
}

const stagedOf = (html: string): string => /name="staged" value="([^"]+)"/.exec(html)?.[1] ?? "";
const importCalls = (w: World) => w.conduit.calls.filter((c) => c.path.endsWith("/release/import"));
const staged = (w: World): string[] => w.store.keys().filter((k) => k.startsWith("pages-staged:"));

async function checked(w: World, token: string, extra: Record<string, string> = {}) {
  return w.post("/studio/releases", { case: CASE_ID, staged: token, action: "check", ...extra });
}

describe("Releases: the page (Scenario S, Releases)", () => {
  it("SR1: a case that loads into no dataset says there is nothing to release; otherwise the intro says what a release carries and never carries", async () => {
    const bare = await make(person({ cases: [caseRow({ datasets: [], dataset_ids: [] })] }));
    const none = await bare.get(PAGE);
    expect(textOf(none.text)).toContain("This case loads into no dataset, so there is nothing to release.");
    expect(none.text).not.toContain('name="export"');
    const w = await make();
    const res = await w.get(PAGE);
    expect(textOf(res.text)).toContain(
      "A release carries this dataset's domain model, its published pipelines and its reference lists' definitions to another environment, as YAML. It never carries a credential, loaded data, case membership, an owner, or a licensed screening list's rows.",
    );
    expect(res.text).toMatch(/<h1>[^<]*Releases?[^<]*<\/h1>|<h2[^>]*>Releases?<\/h2>|<h3[^>]*>Export<\/h3>/);
  });

  it("SR2: export offers the name and version fields with their defaults, asks the Conduit with the person's token, and says how many files it has, what it left out and how to keep them", async () => {
    const w = await make(person({ leftOut: 2 }));
    const form = await w.get(PAGE);
    expect(form.text).toMatch(/<form method="get" action="\/studio\/releases"/);
    expect(form.text).toMatch(/<label[^>]*>\s*<span>Release name<\/span>\s*<input [^>]*name="name"[^>]*value="harbour-prison-extract-synthetic"/);
    expect(form.text).toMatch(/<label[^>]*>\s*<span>Release version<\/span>\s*<input [^>]*name="version"[^>]*value="1"/);
    expect(w.conduit.calls.some((c) => c.path.endsWith("/release"))).toBe(false); // nothing is exported until it is asked for
    const res = await w.get(`${PAGE}&name=wing-release&version=2&export=1`);
    const call = w.conduit.calls.find((c) => c.path === `/v1/datasets/${DATASET}/release`);
    expect(call?.query.get("name")).toBe("wing-release");
    expect(call?.query.get("version")).toBe("2");
    expect(call?.headers["authorization"]).toBe(`Bearer ${w.me.token}`);
    const text = textOf(res.text);
    expect(text).toContain("The release has 3 files. 2 published pipeline(s) are marked above what you may view, so they are not in it.");
    expect(res.text).toMatch(/<p role="status">/);
    expect(res.text).toMatch(/<ul aria-label="The release's files">/);
    for (const path of Object.keys(EXPORT_FILES)) expect(text).toContain(path);
    expect(text).toContain(`To keep the files as a folder, run: ospreyflow release export ${DATASET} --name wing-release --release-version 2 --out <folder>`);
    // The name and version typed stay in the fields.
    expect(res.text).toMatch(/name="name"[^>]*value="wing-release"/);
    expect(res.text).toMatch(/name="version"[^>]*value="2"/);
  });

  it("SR3: an export the Conduit refuses is said in its own words in an alert; a dataset that is not the person's and a right they do not hold read exactly alike, naming neither", async () => {
    const w = await make();
    const bad = await w.get(`${PAGE}&name=Bad%20Name&version=1&export=1`);
    expect(bad.text).toMatch(/<p role="alert">[^<]*is not a name Kubernetes takes/);
    // A person with every right but a dataset none of their cases reads, and a person with the case but not the rights.
    const stranger = await make(person({ datasetsDenied: [DATASET] }));
    const hiddenDataset = await stranger.get(`${PAGE}&export=1`);
    const noRights = await make(person({ rights: ["edit_target_model"] }));
    noRights.conduit.failing.add("/me/rights"); // rights unknown: the page offers the export and the Conduit answers for itself
    const forbidden = await noRights.get(`${PAGE}&export=1`);
    const said = (html: string): string => /<p role="alert">([^<]*)<\/p>/.exec(html)?.[1] ?? "";
    expect(said(forbidden.text)).toBe(REFUSED_BODY("The export"));
    expect(said(hiddenDataset.text)).toBe(REFUSED_BODY("The export"));
    for (const page of [forbidden, hiddenDataset]) {
      expect(page.text).not.toContain("Missing right");
      expect(page.text).not.toContain("edit_target_model");
      expect(page.text).not.toContain("Not Found");
    }
    // A Conduit that does not know the session's bearer.
    const lost = await make();
    lost.conduit.people.clear();
    const ended = await lost.get(`${PAGE}&export=1`);
    expect(said(ended.text)).toContain("Sign in again");
  });

  it("SR4: without Edit domain model and Publish pipelines the export is a real disabled control with the reason beside it, the Conduit is never asked, and a forced address is refused in words", async () => {
    const w = await make(person({ rights: ["edit_pipelines"] }));
    const res = await w.get(PAGE);
    expect(res.text).toMatch(/<input [^>]*name="name"[^>]*disabled/);
    expect(res.text).toMatch(/<input [^>]*name="version"[^>]*disabled/);
    expect(textOf(res.text)).toContain("Exporting needs Edit domain model and Publish pipelines.");
    const forced = await w.get(`${PAGE}&export=1`);
    expect(textOf(forced.text)).toContain("Exporting needs Edit domain model and Publish pipelines.");
    expect(textOf(forced.text)).not.toContain("The release has");
    const file = await w.get(`${PAGE}&download=model.yaml`);
    expect(file.status).toBe(403);
    expect(file.headers["content-disposition"]).toBeUndefined();
    expect(w.conduit.calls.filter((c) => c.path.includes("/release"))).toEqual([]);
  });

  it("SR5: each file downloads from a route of the page, re-asked of the Conduit, as an attachment named by its path; a name the release does not hold is not served", async () => {
    const w = await make();
    const page = await w.get(`${PAGE}&name=wing&version=1&export=1`);
    expect(page.text).toContain(`href="/studio/releases?case=${CASE_ID}&amp;name=wing&amp;version=1&amp;download=pipelines%2Fvisits.yaml"`);
    expect(page.text).toMatch(/<a [^>]*download="pipelines__visits\.yaml"[^>]*>pipelines\/visits\.yaml<\/a>/);
    const res = await w.get(`${PAGE}&name=wing&version=1&download=pipelines%2Fvisits.yaml`);
    expect(res.status).toBe(200);
    expect(res.headers["content-disposition"]).toBe('attachment; filename="pipelines__visits.yaml"');
    expect(res.headers["content-type"]).toMatch(/^application\/yaml/);
    expect(res.headers["x-content-type-options"]).toBe("nosniff");
    expect(res.text).toBe(EXPORT_FILES["pipelines/visits.yaml"]);
    expect(w.conduit.calls.filter((c) => c.path.endsWith("/release")).length).toBe(2); // asked again, never kept
    const odd = await w.get(`${PAGE}&name=wing&version=1&download=..%2Fsecret.yaml`);
    expect(odd.status).toBe(404);
    expect(odd.headers["content-disposition"]).toBeUndefined();
    expect(textOf(odd.text)).toContain("That file is not in the release.");
    // A refusal by the Conduit is the same page of words, with no file.
    const stranger = await make(person({ datasetsDenied: [DATASET] }));
    const refused = await stranger.get(`${PAGE}&name=wing&version=1&download=model.yaml`);
    expect(refused.status).toBe(404);
    expect(refused.headers["content-disposition"]).toBeUndefined();
  });

  it("SR6: a folder sent as a form is read with its paths kept and the folder's own name taken off, and held for the check; nothing is sent to the Conduit yet", async () => {
    const w = await make();
    const res = await upload(w);
    expect(res.status).toBe(200);
    expect(textOf(res.text)).toContain("Read 2 files from the folder.");
    expect(stagedOf(res.text)).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(importCalls(w)).toEqual([]);
    const check = await checked(w, stagedOf(res.text));
    expect(check.status).toBe(200);
    const sent = JSON.parse(importCalls(w)[0]?.body ?? "{}") as { files: Record<string, string> };
    expect(Object.keys(sent.files).sort()).toEqual(["pipelines/visits.yaml", "release.yaml"]);
    expect(sent.files["release.yaml"]).toContain("apiVersion: ospreyflow.io/v1");
    // A file at the top with no folder keeps its name, as `bundleFromFolder` does.
    const loose = await upload(w, [{ path: "release.yaml", text: "apiVersion: ospreyflow.io/v1\n" }]);
    await checked(w, stagedOf(loose.text));
    expect(Object.keys((JSON.parse(importCalls(w)[1]?.body ?? "{}") as { files: object }).files)).toEqual(["release.yaml"]);
    // A name that climbs out of the folder, or is absolute, is refused in words and holds nothing.
    for (const path of ["bundle/../../etc/passwd", "/abs/release.yaml", "bundle/a\\\\b.yaml"]) {
      const bad = await upload(w, [{ path, text: "x" }]);
      expect(textOf(bad.text), path).toContain("A file in the folder has a name a release cannot use.");
      expect(stagedOf(bad.text)).toBe("");
    }
  });

  it("SR7: Check sends the whole bundle as JSON with dry_run=true and shows the plan in words: what it would write, the connection this environment lacks, and the notes", async () => {
    const w = await make();
    const token = stagedOf((await upload(w)).text);
    const res = await checked(w, token);
    const call = importCalls(w)[0];
    expect(call?.method).toBe("POST");
    expect(call?.query.get("dry_run")).toBe("true");
    expect(call?.query.has("replace_own_draft")).toBe(false);
    expect(call?.headers["content-type"]).toMatch(/application\/json/);
    expect(call?.headers["authorization"]).toBe(`Bearer ${w.me.token}`);
    const text = textOf(res.text);
    expect(text).toContain("Would write Wing phone calls as a new draft.");
    expect(text).toContain("This environment has no connection named “warehouse-read”: add one in Admin › Connections before a run.");
    expect(text).toContain("Note: the release was made for version 1.");
    expect(res.text).toMatch(/aria-label="What the import writes"/);
    // A refused check says nothing was written, in an alert, and Import stays shut.
    const noRelease = await upload(w, [{ path: "bundle/model.yaml", text: "packs: {}\n" }]);
    const refused = await checked(w, stagedOf(noRelease.text));
    expect(refused.text).toMatch(/<div role="alert">\s*<p>Nothing was written, because:<\/p>\s*<ul>\s*<li>release\.yaml is missing from the folder<\/li>/);
    expect(/<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(refused.text)?.[0]).toMatch(/\bdisabled\b/);
  });

  it("SR8: Import is offered only after a clean check, writes with dry_run=false, says what it wrote and that everything is a draft, and says nothing went live", async () => {
    const w = await make();
    const first = await upload(w);
    const token = stagedOf(first.text);
    expect(/<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(first.text)?.[0]).toMatch(/\bdisabled\b/);
    expect(textOf(first.text)).toContain("Check the folder first: the import is offered once the check finds nothing wrong.");
    // Forced before a check: refused in words, the Conduit never asked to write.
    const forced = await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import" });
    expect(textOf(forced.text)).toContain("Check the folder first: the import is offered once the check finds nothing wrong.");
    expect(importCalls(w)).toEqual([]);
    const clean = await checked(w, token);
    expect(/<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(clean.text)?.[0]).not.toMatch(/\bdisabled\b/);
    const done = await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import" });
    const write = importCalls(w).at(-1);
    expect(write?.query.get("dry_run")).toBe("false");
    expect(write?.query.has("replace_own_draft")).toBe(false);
    const text = textOf(done.text);
    expect(text).toContain("Wrote Wing phone calls as a new draft.");
    expect(text).toContain(DRAFTS);
    expect(text).not.toMatch(/\bis live\b|\bmade live\b|went live/);
    expect(w.conduit.written).toHaveLength(1);
    // Import is not offered a second time for what was written.
    expect(done.text).not.toMatch(/<button\b[^>]*>\s*Import as drafts\s*<\/button>/);
    const again = await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import" });
    expect(w.conduit.written).toHaveLength(1);
    expect(textOf(again.text)).toContain("That folder is no longer held. Choose the folder again.");
  });

  it("SR9: an importer's own draft is replaced only once they say so, with the version the check named; ticking it checks again, and without scripts a button does", async () => {
    const w = await make(person({ ownDraft: 3 }));
    const token = stagedOf((await upload(w)).text);
    const first = await checked(w, token);
    expect(textOf(first.text)).toContain("your own in-progress draft");
    expect(textOf(first.text)).toContain("Replace my draft of the domain model");
    expect(textOf(first.text)).toContain(
      "You have a draft of this dataset's domain model open. Importing replaces it, and what you have not made live in 1 Model is lost.",
    );
    expect(first.text).toMatch(/<input type="checkbox" name="replace" value="1"[^>]*>/);
    expect(first.text).toMatch(/<button\b[^>]*>\s*Check again, replacing my draft\s*<\/button>/);
    expect(/<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(first.text)?.[0]).toMatch(/\bdisabled\b/);
    expect(importCalls(w)[0]?.query.has("replace_own_draft")).toBe(false);
    // A forced import is refused before the Conduit is asked: the check was not clean.
    await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import", replace: "1" });
    expect(w.conduit.written).toEqual([]);
    const second = await checked(w, token, { replace: "1" });
    expect(importCalls(w).at(-1)?.query.get("dry_run")).toBe("true");
    expect(importCalls(w).at(-1)?.query.get("replace_own_draft")).toBe("3");
    expect(textOf(second.text)).toContain("Would write Wing phone calls as the draft, in place of the one open now.");
    expect(second.text).toMatch(/<input type="checkbox" name="replace" value="1"[^>]* checked/);
    expect(/<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(second.text)?.[0]).not.toMatch(/\bdisabled\b/);
    await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import" });
    expect(importCalls(w).at(-1)?.query.get("dry_run")).toBe("false");
    expect(importCalls(w).at(-1)?.query.get("replace_own_draft")).toBe("3");
    expect(w.conduit.written[0]?.replace).toBe("3");
  });

  it("SR9: a confirmation the importer did not give is never sent, and a version typed into the form is never taken", async () => {
    const w = await make();
    const token = stagedOf((await upload(w)).text);
    await checked(w, token);
    expect((await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import", replace: "1" })).status).toBe(200);
    expect(importCalls(w).at(-1)?.query.has("replace_own_draft")).toBe(false);
    const other = await make(person({ ownDraft: 3 }));
    const held = stagedOf((await upload(other)).text);
    await checked(other, held);
    await checked(other, held, { replace: "1", replace_own_draft: "99", own_draft_version: "99" });
    expect(importCalls(other).at(-1)?.query.get("replace_own_draft")).toBe("3");
  });

  it("SR10: a refusal at the write is shown as a refused check, nothing is marked written, and a new check goes on from it", async () => {
    const w = await make();
    const token = stagedOf((await upload(w)).text);
    await checked(w, token);
    w.conduit.refuseNextWrite = ["the domain model has an in-progress draft (version 3) by analyst-7: an import never replaces another person's draft"];
    const refused = await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import" });
    expect(refused.text).toMatch(/<p>Nothing was written, because:<\/p>/);
    expect(textOf(refused.text)).toContain("an import never replaces another person's draft");
    expect(textOf(refused.text)).not.toContain(DRAFTS);
    expect(/<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(refused.text)?.[0]).toMatch(/\bdisabled\b/);
    expect(w.conduit.written).toEqual([]);
    expect(staged(w)).toHaveLength(1); // still held: the person goes on from it
    const again = await checked(w, token);
    expect(textOf(again.text)).toContain("Would write Wing phone calls as a new draft.");
    expect(/<button\b[^>]*>\s*Import as drafts\s*<\/button>/.exec(again.text)?.[0]).not.toMatch(/\bdisabled\b/);
  });

  it("SR14: with no folder chosen the Check button is shut and says why, and a form sent with no file says so in words", async () => {
    const w = await make();
    const page = await w.get(PAGE);
    const check = /<button\b[^>]*>\s*Check the release\s*<\/button>/.exec(page.text)?.[0] ?? "";
    expect(check).toMatch(/\bdisabled\b/);
    expect(textOf(page.text)).toContain("Choose the release's folder first.");
    const none = await upload(w, []);
    expect(textOf(none.text)).toContain("Choose the release's folder first.");
    expect(stagedOf(none.text)).toBe("");
    expect(staged(w)).toEqual([]);
    // What a browser sends for a folder input with nothing chosen: one file part with an empty name and no bytes.
    const empty = multipart([
      { name: "_csrf", value: w.signed.csrf },
      { name: "case", value: CASE_ID },
      { name: "action", value: "upload" },
      { name: "folder", filename: "", data: Buffer.alloc(0) },
    ]);
    const blank = await request(w.app).post("/studio/releases").set("Cookie", w.signed.cookie).set("Content-Type", empty.type).send(empty.body);
    expect(textOf(blank.text)).toContain("Choose the release's folder first.");
    expect(staged(w)).toEqual([]);
  });

  it("SR15: a problem is said as an alert with the Conduit's own words for a refused plan and fixed words for the rest", async () => {
    const w = await make();
    const token = stagedOf((await upload(w)).text);
    w.conduit.failing.add("/release/import");
    const res = await checked(w, token);
    expect(res.text).toMatch(/<p role="alert">[^<]+<\/p>/);
    expect(textOf(res.text)).toMatch(/The import was refused|could not be carried out|try again/i);
    expect(textOf(res.text)).not.toContain("Internal Server Error");
  });
});

describe("Releases: rights and anti-forgery on every route (rules 3 and 4)", () => {
  it("SR11: without Edit domain model and Edit pipelines the folder is not read, checked or imported, the Conduit is not asked, and the words say why", async () => {
    const w = await make(person({ rights: ["publish_pipelines"] }));
    const page = await w.get(PAGE);
    expect(page.text).toMatch(/<input type="file"[^>]*disabled/);
    expect(textOf(page.text)).toContain("Importing needs Edit domain model and Edit pipelines.");
    const up = await upload(w);
    expect(up.status).toBe(403);
    expect(textOf(up.text)).toContain("Importing needs Edit domain model and Edit pipelines.");
    expect(staged(w)).toEqual([]);
    for (const action of ["check", "import"]) {
      const res = await w.post("/studio/releases", { case: CASE_ID, staged: "x".repeat(43), action });
      expect(res.status, action).toBe(403);
      expect(textOf(res.text)).toContain("Importing needs Edit domain model and Edit pipelines.");
    }
    expect(importCalls(w)).toEqual([]);
    // A person who holds the right for the page but whose case does not read the dataset is told the same as a missing one.
    const stranger = await make(person({ datasetsDenied: [DATASET] }));
    const token = stagedOf((await upload(stranger)).text);
    const refused = await checked(stranger, token);
    expect(textOf(refused.text)).toContain(REFUSED_BODY("The import"));
    expect(refused.text).not.toContain("Not Found");
    expect(stranger.conduit.written).toEqual([]);
  });

  it("SR12: a POST without the right anti-forgery token is refused and does nothing; for an upload the token must be the form's first part, before any file is read", async () => {
    const w = await make();
    expect(staged(w)).toEqual([]);
    for (const csrf of [false as const, "wrong-token"]) {
      const res = await upload(w, FOLDER, { csrf });
      expect(res.status, String(csrf)).toBe(403);
      expect(res.text).not.toContain("Read 2 files");
    }
    const late = await upload(w, FOLDER, { tokenFirst: false });
    expect(late.status).toBe(403);
    expect(staged(w)).toEqual([]);
    for (const action of ["check", "import"]) {
      const none = await w.post("/studio/releases", { case: CASE_ID, staged: "x".repeat(43), action }, false);
      expect(none.status, action).toBe(403);
      const wrong = await w.post("/studio/releases", { case: CASE_ID, staged: "x".repeat(43), action }, "wrong-token");
      expect(wrong.status, action).toBe(403);
    }
    // A token sent in the query string is not a token.
    const inQuery = await request(w.app)
      .post(`/studio/releases?_csrf=${w.signed.csrf}`)
      .set("Cookie", w.signed.cookie)
      .type("form")
      .send({ case: CASE_ID, action: "check", staged: "x".repeat(43) });
    expect(inQuery.status).toBe(403);
    // A multipart post to a page that takes no upload is refused as before.
    const odd = multipart([
      { name: "_csrf", value: w.signed.csrf },
      { name: "folder", filename: "a.yaml", data: Buffer.from("x") },
    ]);
    const wrongPage = await request(w.app).post("/studio").set("Cookie", w.signed.cookie).set("Content-Type", odd.type).send(odd.body);
    expect(wrongPage.status).toBe(403);
    expect(importCalls(w)).toEqual([]);
    // The refusals were the token's: the same upload with the right token, first, is read and held.
    const right = await upload(w);
    expect(right.status).toBe(200);
    expect(staged(w)).toHaveLength(1);
  });
});

describe("Releases: the staged bundle (the session holds it; nothing else does)", () => {
  it("SR13: the bundle is held under a random token in the person's session store, for at most half an hour and never past their session, size-capped, and no more than three at once", async () => {
    const w = await make();
    const res = await upload(w);
    const token = stagedOf(res.text);
    const keys = staged(w);
    expect(keys).toEqual([`pages-staged:${token}`]);
    const ttl = w.store.ttl(keys[0] as string) ?? 0;
    const sessionTtl = w.store.ttl(`pages-session:${w.signed.id}`) ?? 0;
    expect(ttl).toBeGreaterThan(0);
    expect(ttl).toBeLessThanOrEqual(30 * 60);
    expect(ttl).toBeLessThanOrEqual(sessionTtl);
    const tokens = new Set([token]);
    for (let i = 0; i < 3; i += 1) tokens.add(stagedOf((await upload(w)).text));
    expect(tokens.size).toBe(4);
    expect(staged(w)).toHaveLength(3);
    expect(staged(w)).not.toContain(`pages-staged:${token}`); // the oldest went
    // A folder over the cap is refused before it is held, in words.
    const big = await upload(w, [{ path: "bundle/release.yaml", text: "x".repeat(2 * 1024 * 1024 + 1) }]);
    expect(big.status).toBe(413);
    expect(textOf(big.text)).toContain("That folder is larger than the Studio holds for a check (2 MB).");
    expect(staged(w)).toHaveLength(3);
  });

  it("SR13: another session, or another person, cannot use a token: it reads as a folder that is no longer held", async () => {
    const w = await make();
    const token = stagedOf((await upload(w)).text);
    const second = await request(w.app).get("/session/sign-in");
    const otherCookie = (second.headers["set-cookie"] as unknown as string[])[0]?.split(";")[0] as string;
    const page = await request(w.app).get("/").set("Cookie", otherCookie);
    const csrf = /name="_csrf" value="([^"]+)"/.exec(page.text)?.[1] as string;
    const stolen = await request(w.app)
      .post("/studio/releases")
      .set("Cookie", otherCookie)
      .type("form")
      .send({ _csrf: csrf, case: CASE_ID, staged: token, action: "check" });
    expect(textOf(stolen.text)).toContain("That folder is no longer held. Choose the folder again.");
    expect(importCalls(w)).toEqual([]);
    // A made-up token and a token for another key prefix read the same.
    for (const fake of ["a".repeat(43), "../pages-session:x", "pages-session:" + "b".repeat(43)]) {
      const res = await checked(w, fake);
      expect(textOf(res.text)).toContain("That folder is no longer held. Choose the folder again.");
    }
  });

  it("SR13: the bundle is removed after the import, on sign-out, and when it expires", async () => {
    const w = await make();
    const done = stagedOf((await upload(w)).text);
    await checked(w, done);
    await w.post("/studio/releases", { case: CASE_ID, staged: done, action: "import" });
    expect(staged(w)).toEqual([]);
    await upload(w);
    await upload(w);
    expect(staged(w)).toHaveLength(2);
    const out = await w.post("/session/sign-out", {});
    expect(out.status).toBe(303);
    expect(staged(w)).toEqual([]);
    const later = await make();
    await upload(later);
    expect(staged(later)).toHaveLength(1);
    later.clock.advance(31 * 60);
    expect(staged(later)).toEqual([]);
  });

  it("SR15: the bundle is in no log line, no address, no cookie, no page and no page-data block, and the check that looks is shown red against each planted fault", async () => {
    const out = captureOutput();
    const w = await make();
    const responses: Observations["responses"] = [];
    const urls: string[] = [];
    const keep = (res: { text: string; headers: Record<string, unknown> }): void => {
      responses.push({ text: res.text, headers: res.headers });
      const where = res.headers["location"];
      if (typeof where === "string") urls.push(where);
    };
    const up = await upload(w);
    keep(up);
    const token = stagedOf(up.text);
    keep(await checked(w, token));
    keep(await w.get(PAGE));
    keep(await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import" }));
    keep(await w.get(`${PAGE}&staged=${token}`));
    for (const call of w.conduit.calls) urls.push(call.url);
    const seen: Observations = { responses, logs: [...w.logs, out.text()], keys: w.store.keys(), urls };
    out.restore();
    // The bundle did reach the Conduit, so the flow carried it; and it is nowhere else.
    expect(w.conduit.calls.some((c) => c.body.includes(MARKER))).toBe(true);
    expect(findLeaks(MARKER, seen)).toEqual([]);
    for (const response of responses) {
      for (const block of response.text.matchAll(/<script type="application\/json" id="page-data"[^>]*>([\s\S]*?)<\/script>/g)) {
        expect(block[1]).not.toContain(MARKER);
      }
    }
    expect(JSON.stringify(responses.map((r) => r.headers["set-cookie"] ?? ""))).not.toContain(MARKER);
    // Planted faults, in the shape the code would emit each (rule 15): the same check finds them.
    expect(findLeaks(MARKER, { ...seen, logs: [...seen.logs, `pages: studio: import failed for ${MARKER}`] })).toEqual([`log line ${seen.logs.length}`]);
    expect(findLeaks(MARKER, { ...seen, urls: [...seen.urls, `/studio/releases?case=${CASE_ID}&files=${encodeURIComponent(MARKER)}`] })).toHaveLength(1);
    expect(findLeaks(MARKER, { ...seen, responses: [...seen.responses, { text: `<script type="application/json" id="page-data">{"files":"${MARKER}"}</script>`, headers: {} }] })).toHaveLength(1);
    expect(findLeaks(MARKER, { ...seen, responses: [...seen.responses, { text: "", headers: { "set-cookie": [`staged=${MARKER}; Path=/`] } }] })).toHaveLength(1);
    expect(findLeaks(MARKER, { ...seen, keys: [...seen.keys, `pages-staged:${MARKER}`] })).toHaveLength(1);
  });

  it("SR15: the page's own log lines never carry the bundle when the Conduit fails or refuses", async () => {
    const out = captureOutput();
    const w = await make();
    const token = stagedOf((await upload(w)).text);
    w.conduit.failing.add("/release/import");
    await checked(w, token);
    await w.post("/studio/releases", { case: CASE_ID, staged: token, action: "import" });
    const lines = [...w.logs, out.text()];
    out.restore();
    expect(importCalls(w).length).toBeGreaterThan(0); // the failing calls were really made
    expect(findLeaks(MARKER, { responses: [], logs: lines, keys: [], urls: [] })).toEqual([]);
    expect(lines.join("\n")).not.toContain(w.me.token);
  });
});

describe("Releases: words and the page's shape", () => {
  it("SR16: the page's words never say 'target model', never say anything went live, and the page needs no script", async () => {
    const w = await make(person({ ownDraft: 3 }));
    const token = stagedOf((await upload(w)).text);
    const pages = [await w.get(PAGE), await checked(w, token), await checked(w, token, { replace: "1" }), await w.get(`${PAGE}&export=1`)];
    expect(textOf(pages[1]?.text ?? "")).toContain("importing replaces it");
    expect(textOf(pages[2]?.text ?? "")).toContain("Would write");
    expect(textOf(pages[3]?.text ?? "")).toContain("The release has");
    for (const page of pages) {
      expect(page.text).not.toMatch(/target\s*model/i);
      expect(textOf(page.text)).not.toMatch(/\bmade live\b(?! in 1 Model)|\bis live\b|went live/);
      expect(page.text).not.toMatch(/\sstyle\s*=/i);
      expect(page.text).not.toMatch(/\son[a-z]+\s*=/i);
      expect(page.text).not.toMatch(/<script\b(?![^>]*(?:type="application\/json"|type="module" src="))/);
    }
    // Typed text is lost on a tab switch, as in the React screen: the tab links carry none of it.
    expect(pages[0]?.text).not.toMatch(/href="[^"]*(?:name=|version=)/);
  });

  it("SR16: the form's file input takes a folder, is labelled, and a page with scripts off can read it (a submit button, no script needed)", async () => {
    const w = await make();
    const res = await w.get(PAGE);
    expect(res.text).toMatch(/<form method="post" action="\/studio\/releases" enctype="multipart\/form-data">/);
    expect(res.text).toMatch(/<input type="hidden" name="_csrf" value="[^"]+">\s*<input type="hidden" name="case"/);
    expect(res.text).toMatch(/<input type="file" name="folder" multiple webkitdirectory[^>]*aria-label="Choose the release's folder"|<input type="file" name="folder" multiple webkitdirectory/);
    expect(res.text).toMatch(/<button\b[^>]*>\s*Read the folder\s*<\/button>/);
  });
});
