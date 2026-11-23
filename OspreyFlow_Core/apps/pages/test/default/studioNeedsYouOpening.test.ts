/**
 * The Model place is reached from the page, round 6 of slice IS5a (the verifier's first finding).
 *
 * The Needs-you reminder says proposed link types wait on the Model tab, and the Model tab is a link. Model is not on the pages
 * yet, so both open the Studio in the workspace, which opens on Pipelines unless it has been asked for Model: it takes that
 * request from the tab's own storage (`osprey.needsYou.opening`, `packages/glass-shared/src/admin/needsYou/openings.ts`), where
 * the React screen's own Needs-you jump writes it. The page cannot write another origin's page's storage with no script, but it
 * is the same origin and the same tab: the enhancement script writes the same request when either link is followed. Scripts
 * off, the link opens the Studio in the workspace (a place not yet built, said in `spec/08`), and the words say so.
 *
 * Which test fails if the invariant is broken (rule 12): ON1 if a link that should ask for Model carries no dataset to ask
 * for; ON2 if following one does not write the request, writes it for the wrong dataset, loses another kind's request, or is
 * made by a link that is not Model's; ON3 if the key or the shape drifts from the shared package's (the workspace would take
 * nothing and open on Pipelines, as it did).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { CASE_ID, DATASET, caseRow, person, world } from "../support/studioWorld.js";
import type { World } from "../support/studioWorld.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PAGES = join(HERE, "..", "..");

const open: World[] = [];
async function make(me?: Parameters<typeof world>[0]): Promise<World> {
  const w = await world(me);
  open.push(w);
  return w;
}
afterEach(async () => {
  vi.unstubAllGlobals();
  vi.resetModules();
  while (open.length > 0) await open.pop()?.stop();
});

const withProposals = (n: number) =>
  person({ proposals: [{ dataset_id: DATASET, dataset_name: "Harbour prison extract (synthetic)", to_decide: n }] });

/** The opening tags of every link in `html` that carries the attribute `data-opens-model`. */
const askingForModel = (html: string): string[] => [...html.matchAll(/<a\b[^>]*\bdata-opens-model="[^"]*"[^>]*>/g)].map((m) => m[0]);

describe("the page asks for Model when a link to it is followed", () => {
  it("ON1: Model is a page of this service (slice IS2a), so no link asks the workspace to open on it: not the Model tab, not the reminder, and no other", async () => {
    const w = await make(withProposals(2));
    const res = await w.get(`/studio/releases?case=${CASE_ID}`);
    expect(askingForModel(res.text)).toEqual([]);
    // The Model tab and the reminder are plain links to the page, which the person is taken to; the count is still on the tab.
    const nav = /<nav aria-label="Ingest Studio places">([\s\S]*?)<\/nav>/.exec(res.text)?.[1] ?? "";
    const links = [...nav.matchAll(/<a ([^>]*)>([^<]*)<\/a>/g)];
    expect(links.map((l) => l[2])).toContain("1 Model · 2 proposed");
    expect(links.find((l) => l[2] === "1 Model · 2 proposed")?.[1]).toContain(`href="/studio/model?case=${CASE_ID}"`);
    expect(res.text).toContain(`<a class="btn" href="/studio/model?case=${CASE_ID}" aria-describedby="studio-proposals-tip">`);

    // With no proposals, and with a case that loads into no dataset, nothing asks either.
    const none = await make();
    expect(askingForModel((await none.get(`/studio?case=${CASE_ID}`)).text)).toEqual([]);
    const bare = await make(person({ cases: [caseRow({ datasets: [], dataset_ids: [] })] }));
    expect(askingForModel((await bare.get(`/studio?case=${CASE_ID}`)).text)).toEqual([]);
  });

  it("ON2: following a link that asks writes the request the workspace reads; another kind's request is kept, an earlier Model request replaced", async () => {
    const store = new Map<string, string>();
    store.set("osprey.needsYou.opening", JSON.stringify([{ kind: "admin", section: "operations" }, { kind: "studio", tab: "model", datasetId: "old" }]));
    const listeners = new Map<string, ((event: unknown) => void)[]>();
    const link = (attrs: Record<string, string>) => ({
      getAttribute: (n: string) => attrs[n] ?? null,
      addEventListener: (type: string, fn: (event: unknown) => void) => listeners.set(type + attrs["id"], [...(listeners.get(type + attrs["id"]) ?? []), fn]),
    });
    const model = link({ id: "m", "data-opens-model": "harbour-extract" });
    vi.stubGlobal("sessionStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    });
    vi.stubGlobal("document", {
      querySelectorAll: (selector: string) => (selector.includes("data-opens-model") ? [model] : []),
    });
    await import("../../modules/studio-frame.js");
    expect(listeners.get("clickm")?.length).toBe(1);
    expect(store.get("osprey.needsYou.opening")).toContain("old"); // nothing is written until a link is followed
    for (const fn of listeners.get("clickm") ?? []) fn({});
    expect(JSON.parse(store.get("osprey.needsYou.opening") ?? "null")).toEqual([
      { kind: "admin", section: "operations" },
      { kind: "studio", tab: "model", datasetId: "harbour-extract" },
    ]);
  });

  it("ON2b: a storage that refuses the write does not stop the link being followed", async () => {
    const listeners: ((event: unknown) => void)[] = [];
    vi.stubGlobal("sessionStorage", {
      getItem: () => null,
      setItem: () => {
        throw new Error("storage is off");
      },
      removeItem: () => undefined,
    });
    vi.stubGlobal("document", {
      querySelectorAll: (selector: string) =>
        selector.includes("data-opens-model")
          ? [{ getAttribute: () => "harbour-extract", addEventListener: (_t: string, fn: (event: unknown) => void) => listeners.push(fn) }]
          : [],
    });
    await import("../../modules/studio-frame.js");
    expect(listeners).toHaveLength(1);
    expect(() => listeners.forEach((fn) => fn({ preventDefault: () => expect.unreachable("the link must still be followed") }))).not.toThrow();
  });

  it("ON3: the key and the shape are the shared package's, read from its source, so a change there fails here", () => {
    const shared = readFileSync(join(PAGES, "..", "..", "packages", "glass-shared", "src", "admin", "needsYou", "openings.ts"), "utf8");
    const mine = readFileSync(join(PAGES, "modules", "studio-frame.ts"), "utf8");
    const key = /const KEY = "([^"]+)"/.exec(shared)?.[1];
    expect(key).toBeTruthy();
    expect(mine).toContain(`"${key}"`);
    expect(shared).toMatch(/\{ kind: "studio"; tab: "model"; datasetId: string \}/);
    expect(mine).toMatch(/kind: "studio", tab: "model", datasetId/);
  });
});
