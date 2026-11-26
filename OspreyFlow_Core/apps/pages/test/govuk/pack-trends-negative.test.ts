/**
 * A trend whose period totals go below zero, drawn on the page of trends shown together (slice GR4a, round 3; scenario TS1's "the chart and
 * its table say the same figures"; rule 15). The real route can send one: `TrendPoint.value` and `TrendResult.total` have no lower bound
 * (`packages/schemas/analytics.py`), and a sum of a signed property is below zero in a period where more went out than came in. A bar has
 * no height below zero (the workspace's `TrendChart.tsx` clamps at zero); a negative height is not drawn by a browser, and when every
 * total is below zero a "tallest bar" of 0 is a figure the table does not hold. The page must draw no bar outside its view box, keep the
 * table's figures as they are, and say in the text alternative what the chart leaves out.
 *
 * `pack-trends.test.ts` (frozen) has no signed figure in its fixture, so its same-figures check never met one; this file does.
 */
import { afterEach, describe, expect, it } from "vitest";

import { createApp } from "../../server/app.js";
import { PAGES } from "../../server/pageList.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, request } from "../support/http.js";
import { generateSecret } from "../support/secret.js";
import { bearer, providerFor, textOf } from "../support/studioWorld.js";
import { RECORD_ASSESSMENT, figures, packItem, packsConduit } from "./packsConduit.js";
import type { PacksConduit } from "./packsConduit.js";

const CASE = "case-estuary";
const conduits: PacksConduit[] = [];
afterEach(async () => {
  while (conduits.length > 0) await conduits.pop()?.stop();
});

const WEEKS = ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"];

/** A pack with one sum trend, one total for each of four weeks, as the page is given it. */
async function pageOf(totals: number[]): Promise<string> {
  const token = bearer();
  const item = packItem({
    id: "item-ledger",
    kind: "trend",
    trend_id: "trend-ledger",
    trend: figures({
      title: "Ledger movements",
      definition: { measure: "sum", measure_field: "amount" },
      result: { measure: "sum", total: totals.reduce((a, b) => a + b, 0), events: 4, unvalued: 0 },
      points: totals.map((value, i) => ({ period_start: `${WEEKS[i] as string}T00:00:00Z`, value })),
    }),
  });
  const conduit = await packsConduit({
    readers: [{ token, rights: [RECORD_ASSESSMENT], cases: { [CASE]: "viewer" } }],
    cases: [CASE],
    packs: [
      {
        id: "pack-estuary",
        case_id: CASE,
        title: "Estuary movements",
        created_by: "someone-synthetic",
        created_at: "2026-11-01T09:00:00Z",
        updated_at: "2026-11-02T12:00:00Z",
        items: [{ item }],
      },
    ],
  });
  conduits.push(conduit);
  const app = createApp({
    store: new MemorySessionStore({ clock: testClock() }),
    identityProvider: providerFor(token),
    sessionSecret: generateSecret(48),
    pages: PAGES,
    tree: "govuk",
    forward: { conduitUrl: conduit.url, bodyMaxBytes: 1024, uploadMaxBytes: 1024, upstreamTimeoutSeconds: 2 },
  });
  const signIn = await request(app).get("/session/sign-in");
  const cookie = cookieFrom(signIn);
  const res = await request(app).get(`/packs/trends?case=${CASE}&pack=pack-estuary`).set("Cookie", cookie);
  expect(res.status).toBe(200);
  return res.text;
}

interface Drawn {
  label: string;
  viewBoxHeight: number;
  bars: { y: number; height: number }[];
  totals: string[];
}

function drawn(html: string): Drawn {
  const svg = /<svg\b([^>]*)>([\s\S]*?)<\/svg>/.exec(html);
  if (!svg) throw new Error("no chart");
  const viewBox = /viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"/.exec(svg[1] as string);
  const rects = [...(svg[2] as string).matchAll(/<rect\b([^>]*)>/g)].map((m) => {
    const num = (name: string): number => Number(new RegExp(`\\s${name}="([^"]*)"`).exec(m[1] as string)?.[1]);
    return { y: num("y"), height: num("height") };
  });
  const body = /<tbody\b[^>]*>([\s\S]*?)<\/tbody>/.exec(html)?.[1] ?? "";
  const totals = [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map((row) => {
    const cells = [...(row[1] as string).matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g)].map((c) => textOf(c[1] as string));
    return cells[cells.length - 1] ?? "";
  });
  return { label: textOf(/<title\b[^>]*>([\s\S]*?)<\/title>/.exec(svg[2] as string)?.[1] ?? ""), viewBoxHeight: Number(viewBox?.[2]), bars: rects, totals };
}

/** What no chart may hold: a bar with a height below zero, or one that starts or ends outside its view box. */
const outsideProblems = (d: Drawn): string[] =>
  d.bars.flatMap((bar, i) => (bar.height < 0 || bar.y < 0 || bar.y + bar.height > d.viewBoxHeight + 0.01 ? [`bar ${i} (y ${bar.y}, height ${bar.height}) is outside the chart`] : []));

describe("a trend whose totals go below zero (the govuk tree)", () => {
  it("draws no bar below zero, keeps the table's figures, and says what the chart leaves out", async () => {
    const d = drawn(await pageOf([-5, 3, 0, 4]));
    expect(d.totals).toEqual(["-5", "3", "0", "4"]);
    expect(outsideProblems(d)).toEqual([]);
    // A period below zero has no height; the others stay in proportion to the tallest, which is the table's own 4.
    expect(d.bars.map((b) => b.height)).toEqual([0, 75, 0, 100]);
    expect(d.label).toContain("the tallest bar is 4");
    expect(d.label).toMatch(/below zero has no height, and the table gives every figure/);
  });

  it("with every total below zero says no bar has any height, and never a tallest bar of 0 that the table does not hold", async () => {
    const d = drawn(await pageOf([-5, -2, -1, -3]));
    expect(d.totals).toEqual(["-5", "-2", "-1", "-3"]);
    expect(outsideProblems(d)).toEqual([]);
    expect(d.bars.map((b) => b.height)).toEqual([0, 0, 0, 0]);
    expect(d.label).not.toMatch(/tallest bar/);
    expect(d.label).toContain("no bar has any height, as no total is above zero");
  });

  it("leaves a trend with no total below zero as it was: no sentence about heights, the tallest bar said", async () => {
    const d = drawn(await pageOf([2, 0, 4, 1]));
    expect(d.bars.map((b) => b.height)).toEqual([50, 0, 100, 25]);
    expect(d.label).toBe("Ledger movements: one bar for each of 4 weeks, from 5 October 2026 to 26 October 2026; the tallest bar is 4.");
  });

  it("the check finds the fault it names: the page as it was drew a bar of height -166.67 for totals of -5 and 3", () => {
    const old: Drawn = { label: "", viewBoxHeight: 100, bars: [{ y: 266.67, height: -166.67 }, { y: 0, height: 100 }], totals: ["-5", "3"] };
    expect(outsideProblems(old)).toHaveLength(1);
  });
});
