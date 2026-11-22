/**
 * The readiness strip's three reads need a right each, as the real Conduit decides (slice IS5a, round 7; rule 15). The page
 * reads `recipe-registry` (Edit pipelines), a pipeline's `runs` (Run pipelines) and a dataset's `sources` (Add ingest files)
 * as the person. A person without one of them is refused (403), and a refusal is not "try again in a few minutes": it says
 * what it is, in the Conduit's own kind of words, and never shows a failed read as an empty answer.
 *
 * Which test fails if the invariant is broken (rule 12):
 *  - a fake that grants these three reads to anyone (so every strip test passes only against the fake)  -> "the fake refuses"
 *  - a refusal worded as "try again"                                                                    -> "a refusal is not try again"
 *  - a run read the person may not make shown as "no run yet"                                           -> "a last run the person may not read"
 *  - a failing Conduit that stops saying "try again"                                                    -> "a Conduit that fails"
 *  - the strip drawn as the fake's grant for a person who holds the three rights                        -> "with the three rights"
 */
import { afterEach, describe, expect, it } from "vitest";

import { CASE_ID, person, textOf, world } from "../support/studioWorld.js";
import type { World } from "../support/studioWorld.js";

const open: World[] = [];
async function make(...args: Parameters<typeof world>): Promise<World> {
  const w = await world(...args);
  open.push(w);
  return w;
}
afterEach(async () => {
  while (open.length > 0) await open.pop()?.stop();
});

const TRY_AGAIN = "Try again in a few minutes";
const PIPELINES_REFUSED = "Reading the pipelines is not available to you: it needs rights you do not hold, or the dataset is not one of yours.";
const PUBLISHED = [{ recipe_id: "r1", status: "published", source_location: "calls.csv" }];

async function ask(w: World, path: string): Promise<{ status: number; body: unknown }> {
  const res = await fetch(`${w.conduit.url}${path}`, { headers: { Authorization: `Bearer ${w.me.token}` } });
  return { status: res.status, body: await res.json() };
}

describe("the fake Conduit refuses what the real one refuses (rule 15)", () => {
  it("the fake refuses: the registry without Edit pipelines, the runs without Run pipelines, the sources without Add ingest files", async () => {
    const w = await make(person({ rights: ["edit_target_model"], pipelines: PUBLISHED }));
    const registry = await ask(w, `/v1/investigations/${CASE_ID}/ingest/recipe-registry`);
    const runs = await ask(w, `/v1/investigations/${CASE_ID}/ingest/recipes/r1/runs`);
    const sources = await ask(w, "/v1/datasets/harbour-extract/sources");
    expect([registry.status, runs.status, sources.status]).toEqual([403, 403, 403]);
    expect(registry.body).toEqual({ detail: "Missing right: edit_pipelines" });
    expect(runs.body).toEqual({ detail: "Missing right: run_pipelines" });
    expect(sources.body).toEqual({ detail: "Missing right: add_ingest_files" });
  });

  it("the fake grants each to a person who holds that right: the refusal is the right's own", async () => {
    const w = await make(person({ rights: ["edit_pipelines", "run_pipelines", "add_ingest_files"], pipelines: PUBLISHED }));
    expect((await ask(w, `/v1/investigations/${CASE_ID}/ingest/recipe-registry`)).status).toBe(200);
    expect((await ask(w, `/v1/investigations/${CASE_ID}/ingest/recipes/r1/runs`)).status).toBe(200);
    expect((await ask(w, "/v1/datasets/harbour-extract/sources")).status).toBe(200);
  });

  it("the right is checked before the case, as the real route's dependency runs first: a person without it learns nothing of the case", async () => {
    const w = await make(person({ rights: ["edit_target_model"] }));
    const there = await ask(w, `/v1/investigations/${CASE_ID}/ingest/recipe-registry`);
    const absent = await ask(w, "/v1/investigations/no-such-case/ingest/recipe-registry");
    expect(absent).toEqual(there);
  });
});

describe("the frame for a person the strip's reads refuse", () => {
  it("a refusal is not try again: the pipelines' refusal is said in the Conduit's kind of words, and the strip says it could not read them", async () => {
    const w = await make(person({ rights: ["edit_target_model", "publish_pipelines"] }));
    const res = await w.get(`/studio?case=${CASE_ID}`);
    const text = textOf(res.text);
    expect(res.status).toBe(200);
    expect(text).toContain(PIPELINES_REFUSED);
    expect(res.text).toMatch(/role="alert"[^>]*>\s*Reading the pipelines is not available to you/);
    expect(text).not.toContain(TRY_AGAIN);
    expect(text).toContain("pipelines could not be read");
    expect(text).toContain("sources could not be read");
    // Never shown as an empty answer.
    expect(text).not.toMatch(/\b0 (sources|pipelines)\b/);
    // Nothing the refusal named: no right's identifier on the page.
    expect(res.text).not.toContain("edit_pipelines");
  });

  it("a last run the person may not read is said, not shown as no run yet", async () => {
    const w = await make(person({ rights: ["edit_pipelines", "add_ingest_files"], pipelines: PUBLISHED, runs: { r1: [{ run_id: "x", started_at: "2026-11-20T09:05:00Z", outcome: "success" }] } }));
    const text = textOf((await w.get(`/studio?case=${CASE_ID}`)).text);
    expect(text).toContain("last run could not be read");
    expect(text).not.toContain("no run yet");
    expect(text).not.toContain("success");
    expect(text).not.toContain(TRY_AGAIN);
  });

  it("with the three rights the strip is what the Conduit answered: the sources, the pipelines and the last run", async () => {
    const w = await make(
      person({
        rights: ["edit_pipelines", "run_pipelines", "add_ingest_files"],
        pipelines: PUBLISHED,
        sources: [{ id: "s1", location: "calls.csv", name: "Calls" }],
        runs: { r1: [{ run_id: "x", started_at: "2026-11-20T09:05:00Z", outcome: "success" }] },
      }),
    );
    const text = textOf((await w.get(`/studio?case=${CASE_ID}`)).text);
    expect(text).toContain("1 source");
    expect(text).toContain("1 pipeline");
    expect(text).toContain("last run 20 Nov 2026, 09:05 UTC, success");
    expect(text).not.toContain("could not be read");
  });

  it("a Conduit that fails still says to try again: only a refusal does not", async () => {
    const w = await make(person({ rights: ["edit_pipelines", "run_pipelines", "add_ingest_files"], pipelines: PUBLISHED }));
    w.conduit.failing.add("/recipe-registry");
    const text = textOf((await w.get(`/studio?case=${CASE_ID}`)).text);
    expect(text).toContain("The pipelines could not be read just now. Try again in a few minutes.");
    expect(text).not.toContain(PIPELINES_REFUSED);
  });
});
