/**
 * The Studio's frame as a server-rendered page, Default tree (slice IS5a; ADR-152 decisions 7 and 12; FUNCTIONS row
 * `studio-frame`). Written against today's React screen (`apps/workspace/src/ingest/IngestStudio.tsx`,
 * `studio/ReadinessStrip.tsx`, `studio/rightsGate.tsx`): each case's id is a scenario of `spec/08_ACCEPTANCE_SCENARIOS.md`
 * ("Scenario S"), which names the React words it rebuilds, and `tests/glass_trees/test_studio_frame_scenarios.py` holds
 * the two in step.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a page that shows another person's case or a count the person may not see   -> SF11
 *  - a refusal worded differently for "not allowed" and "no such case"           -> SF11
 *  - a control that needs a right drawn as a live control for someone without it -> SF7
 *  - a silent failure of the case list                                           -> SF10
 *  - a Needs-you jump that does nothing                                          -> SF9
 * The fake Conduit refuses what the real one refuses (`test/support/fakeConduit.ts`, rule 15).
 */
import { afterEach, describe, expect, it } from "vitest";

import { CASE_ID, DATASET, DATASET_NAME, caseRow, person, textOf, world } from "../support/studioWorld.js";
import type { World } from "../support/studioWorld.js";
import { request } from "../support/http.js";

const open: World[] = [];
async function make(...args: Parameters<typeof world>): Promise<World> {
  const w = await world(...args);
  open.push(w);
  return w;
}
afterEach(async () => {
  while (open.length > 0) await open.pop()?.stop();
});

const NO_CASE = "Open a case to use the Ingest Studio: it works on the dataset the case loads into.";
const REFUSED_SWITCH = "None of your cases loads into that dataset, so the Studio cannot open on it.";

describe("the frame (Scenario S, frame)", () => {
  it("SF1: with no case open the page says to open one, and offers no dataset to choose", async () => {
    const w = await make();
    const res = await w.get("/studio");
    expect(res.status).toBe(200);
    expect(textOf(res.text)).toContain(NO_CASE);
    expect(res.text).not.toContain("<select");
    expect(w.conduit.calls.filter((c) => c.path.includes("release"))).toEqual([]);
  });

  it("SF2: the dataset switch lists the datasets the person's cases load into, the open case's first, and a switch goes to the case that serves it", async () => {
    const other = caseRow({ id: "case-other", name: "Other work", datasets: ["Second dataset"], dataset_ids: ["second-ds"] });
    const w = await make(person({ cases: [caseRow(), other] }));
    const page = await w.get(`/studio?case=${CASE_ID}`);
    expect(page.status).toBe(200);
    const options = [...page.text.matchAll(/<option value="([^"]*)"[^>]*>([^<]*)<\/option>/g)].map((m) => [m[1], m[2]]);
    expect(options).toEqual([
      [DATASET, DATASET_NAME],
      ["second-ds", "Second dataset"],
    ]);
    expect(page.text).toMatch(/<option value="harbour-extract" selected>/);
    // The switch is a GET form with a button that works with scripts off; the select is labelled.
    expect(page.text).toMatch(/<form method="get" action="\/studio"/);
    expect(page.text).toMatch(/<label[^>]*>\s*(?:<span[^>]*>)?Dataset/);
    expect(page.text).toMatch(/<button type="submit"[^>]*>Switch dataset<\/button>/);
    const switched = await w.get(`/studio?case=${CASE_ID}&dataset=second-ds`);
    expect(switched.status).toBe(303);
    expect(switched.headers["location"]).toBe("/studio?case=case-other");
  });

  it("SF2: a dataset no case of the person's loads into is refused in words, and the page stays on the open case; a case that loads into none says so", async () => {
    const w = await make();
    const refused = await w.get(`/studio?case=${CASE_ID}&dataset=not-mine`);
    expect(refused.status).toBe(200);
    expect(textOf(refused.text)).toContain(REFUSED_SWITCH);
    expect(refused.text).toMatch(/role="alert"[^>]*>[^<]*None of your cases/);
    expect(refused.text).toMatch(/<option value="harbour-extract" selected>/);
    const bare = await make(person({ cases: [caseRow({ datasets: [], dataset_ids: [] })] }));
    const none = await bare.get(`/studio?case=${CASE_ID}`);
    expect(textOf(none.text)).toContain("This case loads into no dataset");
    expect(none.text).toMatch(/<select[^>]*disabled/);
  });

  it("SF3: the page says which case it works through and which dataset what loads goes into", async () => {
    const w = await make();
    const res = await w.get(`/studio?case=${CASE_ID}`);
    expect(textOf(res.text)).toContain(`Working through the case “Wing review”: what loads here goes into ${DATASET_NAME}.`);
  });

  it("SF4: the readiness strip says where the dataset stands, in words, and is not live", async () => {
    const w = await make(
      person({
        pipelines: [
          { recipe_id: "r1", status: "published", source_location: "calls.csv" },
          { recipe_id: "r2", status: "draft", source_location: "visits.csv" },
          { recipe_id: "r0", status: "superseded", source_location: "old.csv" },
        ],
        sources: [{ id: "s1", location: "calls.csv", name: "Calls" }],
        runs: { r1: [{ run_id: "x", started_at: "2026-11-20T09:05:00Z", outcome: "success" }] },
      }),
    );
    const res = await w.get(`/studio?case=${CASE_ID}`);
    const text = textOf(res.text);
    expect(res.text).toMatch(/<ul aria-label="Where this dataset stands"/);
    expect(text).toContain("Model: POLE core");
    expect(text).toContain("1 source · 1 file not registered");
    expect(text).toContain("2 pipelines · 1 untested");
    expect(text).toContain("last run 20 Nov 2026, 09:05 UTC, success");
    // Not live: nothing on the page refreshes itself.
    expect(res.text).not.toMatch(/http-equiv="refresh"/i);
    const empty = await make(person({ pipelines: [] }));
    expect(textOf((await empty.get(`/studio?case=${CASE_ID}`)).text)).toContain("no run yet");
  });

  it("SF4: a sources read that fails is said, never shown as no sources", async () => {
    const w = await make();
    w.conduit.failing.add("/sources");
    const res = await w.get(`/studio?case=${CASE_ID}`);
    expect(textOf(res.text)).toContain("sources could not be read");
    expect(textOf(res.text)).not.toMatch(/\b0 sources\b/);
  });

  it("SF5: proposed link types waiting for the person show a reminder and its tip, and the Model tab's count; a failed count is said, never shown as none", async () => {
    const w = await make(person({ proposals: [{ dataset_id: DATASET, dataset_name: DATASET_NAME, to_decide: 2 }] }));
    const res = await w.get(`/studio/releases?case=${CASE_ID}`);
    const text = textOf(res.text);
    expect(text).toContain("2 proposed link types wait for you on the Model tab.");
    expect(text).toContain("Analysts proposed new link types for this dataset. Decide them on 1 Model");
    expect(text).toContain("1 Model · 2 proposed");
    expect(res.text).toMatch(/<a [^>]*href="[^"]*"[^>]*aria-describedby="studio-proposals-tip"[^>]*>2 proposed link types wait for you on the Model tab\.<\/a>/);
    expect(res.text).toMatch(/<span id="studio-proposals-tip" role="note">/);

    const broken = await make();
    broken.conduit.failing.add("/me/needs-you");
    const said = await broken.get(`/studio/releases?case=${CASE_ID}`);
    expect(textOf(said.text)).toContain("The proposed link types waiting for you could not be counted; the Model tab lists them.");
    expect(said.text).toMatch(/role="status"/);
    expect(textOf(said.text)).not.toContain("wait for you on the Model tab");
  });

  it("SF6: the five places are links, the open one marked, reachable by Tab and Enter; typed text is not carried across (as in the React screen)", async () => {
    const w = await make();
    const res = await w.get(`/studio/releases?case=${CASE_ID}&name=typed-text&version=9`);
    const nav = /<nav aria-label="Ingest Studio places">([\s\S]*?)<\/nav>/.exec(res.text)?.[1] ?? "";
    const links = [...nav.matchAll(/<a ([^>]*)>([^<]*)<\/a>/g)].map((m) => ({ attrs: m[1] as string, label: m[2] as string }));
    expect(links.map((l) => l.label)).toEqual(["1 Model", "2 Sources", "3 Pipelines", "4 Runs", "5 Releases"]);
    const releases = links[4] as { attrs: string };
    expect(releases.attrs).toContain(`href="/studio/releases?case=${CASE_ID}"`);
    expect(releases.attrs).toContain('aria-current="page"');
    expect(links.filter((l) => l.attrs.includes("aria-current"))).toHaveLength(1);
    // Every place is a link with an address and no tabindex that takes it out of the Tab order; no link carries typed text.
    for (const link of links) {
      expect(link.attrs).toMatch(/href="[^"]+"/);
      expect(link.attrs).not.toContain("tabindex");
      expect(link.attrs).not.toContain("typed-text");
    }
    // Model is a page of this service (slice IS2a); the places not yet on the pages open the Studio in the workspace, on the same case.
    expect(links[0]?.attrs).toContain(`href="/studio/model?case=${CASE_ID}"`);
    for (const place of links.slice(1, 4)) expect(place.attrs).toContain(`href="/?investigation=${CASE_ID}&amp;from=case&amp;view=ingest"`);
  });

  it("SF7: a control that needs a right is a real disabled control with the reason as text beside it, from the person's rights as the Conduit answers; unknown rights offer it as before", async () => {
    const w = await make(person({ rights: ["edit_pipelines"] }));
    const res = await w.get(`/studio/releases?case=${CASE_ID}`);
    const button = /<button\b[^>]*>\s*Export\s*<\/button>/.exec(res.text)?.[0] ?? "";
    expect(button).toMatch(/\bdisabled\b/);
    expect(button).toContain('aria-describedby="why-export"');
    expect(res.text).toMatch(/<span id="why-export"[^>]*data-why-not[^>]*>You need Edit domain model\. Ask an administrator to give it to you\.<\/span>/);
    // The right's name, never its identifier.
    expect(res.text).not.toContain("edit_target_model");
    const unknown = await make();
    unknown.conduit.failing.add("/me/rights");
    const offered = await unknown.get(`/studio/releases?case=${CASE_ID}`);
    expect(/<button\b[^>]*>\s*Export\s*<\/button>/.exec(offered.text)?.[0]).not.toMatch(/\bdisabled\b/);
  });

  it("SF8: the help is a panel in the page, so typed text survives opening it: it is in the same document, opens with no navigation, and says the person's own roles and rights", async () => {
    const w = await make(person({ roles: ["data_engineer"] }));
    const res = await w.get(`/studio/releases?case=${CASE_ID}`);
    const panel = /<details id="studio-help"[^>]*>([\s\S]*?)<\/details>/.exec(res.text)?.[1] ?? "";
    expect(panel).toContain("<summary>Roles, teams and Authors</summary>");
    expect(textOf(panel)).toContain("data_engineer");
    expect(textOf(panel)).toContain("Edit domain model");
    // No navigation: nothing in the panel is a link that leaves the page, and it is not a form that submits.
    expect(panel).not.toMatch(/<a [^>]*href="(?!#)/);
    expect(panel).not.toContain("<form");
    // The panel and the Releases form are in one document: opening the panel cannot lose what is typed in the form.
    expect(res.text.indexOf('id="studio-help"')).toBeGreaterThan(-1);
    expect(res.text.indexOf('name="name"')).toBeGreaterThan(-1);
    expect(res.text.match(/<html\b/g)).toHaveLength(1);
  });

  it("SF9: a Needs-you jump is a link carrying the request, which the page reads and shows; for another dataset it opens the case that serves it, and for none it says so", async () => {
    const other = caseRow({ id: "case-other", name: "Other work", datasets: ["Second dataset"], dataset_ids: ["second-ds"] });
    const w = await make(
      person({
        cases: [caseRow(), other],
        proposals: [
          { dataset_id: DATASET, dataset_name: DATASET_NAME, to_decide: 2 },
          { dataset_id: "second-ds", dataset_name: "Second dataset", to_decide: 1 },
        ],
      }),
    );
    const here = await w.get(`/studio?case=${CASE_ID}&opening=model&dataset=${DATASET}`);
    expect(here.status).toBe(200);
    expect(textOf(here.text)).toContain(`Needs you sent you here: 2 proposed link types to decide in ${DATASET_NAME}. They are on 1 Model.`);
    expect(here.text).toMatch(/<a [^>]*aria-current="page"[^>]*>1 Model · 2 proposed<\/a>|<a [^>]*>1 Model · 2 proposed<\/a>/);
    const elsewhere = await w.get(`/studio?case=${CASE_ID}&opening=model&dataset=second-ds`);
    expect(elsewhere.status).toBe(303);
    expect(elsewhere.headers["location"]).toBe("/studio?case=case-other&opening=model&dataset=second-ds");
    const none = await w.get(`/studio?case=${CASE_ID}&opening=model&dataset=not-mine`);
    expect(none.status).toBe(200);
    expect(textOf(none.text)).toContain(REFUSED_SWITCH);
    expect(textOf(none.text)).not.toContain("Needs you sent you here");
    // A request for anything but the Model tab is not a request the Studio takes.
    const odd = await w.get(`/studio?case=${CASE_ID}&opening=elsewhere&dataset=${DATASET}`);
    expect(textOf(odd.text)).not.toContain("Needs you sent you here");
  });

  it("SF10: a case list that cannot be read is said in words, not left as an empty Studio", async () => {
    const w = await make();
    w.conduit.failing.add("/v1/investigations");
    const res = await w.get(`/studio?case=${CASE_ID}`);
    expect(res.status).toBe(200);
    expect(textOf(res.text)).toContain(
      "Your cases could not be read just now, so the Studio cannot say which dataset it is open on. Try again in a few minutes.",
    );
    expect(res.text).toMatch(/role="alert"/);
  });
});

describe("the frame's access control (rules 3 and 4)", () => {
  it("SF11: a signed-out request is sent to sign-in on every Studio path, and nothing is asked of the Conduit", async () => {
    const w = await make();
    for (const path of ["/studio", `/studio?case=${CASE_ID}`, `/studio/releases?case=${CASE_ID}`]) {
      const res = await request(w.app).get(path);
      expect(res.status, path).toBe(302);
      expect(res.headers["location"]).toBe("/session/sign-in");
    }
    expect(w.conduit.calls).toEqual([]);
  });

  it("SF11: every call to the Conduit carries the person's bearer and nothing of the browser's: not its cookie, its anti-forgery token or its address", async () => {
    const w = await make();
    await w.get(`/studio/releases?case=${CASE_ID}`).set("X-CSRF-Token", w.signed.csrf).set("Origin", "https://evil.test");
    expect(w.conduit.calls.length).toBeGreaterThan(0);
    for (const call of w.conduit.calls) {
      expect(call.headers["authorization"], call.path).toBe(`Bearer ${w.me.token}`);
      expect(call.headers["cookie"]).toBeUndefined();
      expect(call.headers["x-csrf-token"]).toBeUndefined();
      expect(call.headers["origin"]).toBeUndefined();
      expect(call.url).not.toContain(w.me.token);
      expect(call.url).not.toContain(w.signed.csrf);
    }
  });

  it("SF11: a case the person may not open reads exactly as one that does not exist, and shows nothing of it or of what it holds", async () => {
    const hidden = caseRow({ id: "case-hidden", name: "Someone else's secret case", datasets: ["Hidden dataset"], dataset_ids: ["hidden-ds"] });
    const w = await make(
      person({ proposals: [{ dataset_id: "hidden-ds", dataset_name: "Hidden dataset", to_decide: 7 }] }),
    );
    // `hidden` is in nobody's list here: the fake Conduit gives this person only their own case.
    void hidden;
    const missing = await w.get("/studio?case=case-does-not-exist");
    const refused = await w.get("/studio?case=case-hidden");
    expect(refused.status).toBe(missing.status);
    const strip = (html: string): string => textOf(html).replace(/case-(?:does-not-exist|hidden)/g, "case-x");
    expect(strip(refused.text)).toBe(strip(missing.text));
    for (const page of [missing, refused]) {
      expect(page.text).not.toContain("Someone else's secret case");
      expect(page.text).not.toContain("Hidden dataset");
      expect(page.text).not.toMatch(/\b7\b[^<]*proposed/);
    }
    // A count for a dataset the person has no case for is never drawn.
    const mine = await w.get(`/studio?case=${CASE_ID}`);
    expect(textOf(mine.text)).toContain("Working through the case “Wing review”"); // the page is there, and shows only what is theirs
    expect(mine.text).not.toContain("Hidden dataset");
    expect(textOf(mine.text)).not.toContain("7 proposed");
  });

  it("SF11: the frame answers in the Default tree's layout, with no script that the page needs, no inline style and no inline handler", async () => {
    const w = await make();
    const res = await w.get(`/studio/releases?case=${CASE_ID}`);
    expect(res.status).toBe(200);
    expect(textOf(res.text)).toContain("Export");
    expect(res.text).toMatch(/lang="en-GB"/);
    expect(res.text).not.toMatch(/\sstyle\s*=/i);
    expect(res.text).not.toMatch(/\son[a-z]+\s*=/i);
    expect(res.text).not.toMatch(/javascript:/i);
    expect(res.text).not.toMatch(/target model/i);
    expect(res.headers["cache-control"]).toBe("no-store");
  });
});
