// ADR-113 stage 5: the print document. Each item's page carries THAT item's own marking, top and
// bottom, never the pack's level; the cover says what is withheld only when a number says so; every
// string put into the HTML is escaped; every item in the manifest has a page.
import { describe, expect, it } from "vitest";

import { escapeHtml, packPrintHtml } from "./packExport";
import { NOTE_ITEM, TREND_ITEM, manifest } from "./reportsTestKit";
import type { PackItem } from "../../../../packages/schemas/generated";

const OFFICIAL_NOTE: PackItem = { ...NOTE_ITEM, id: "n1", marking: "OFFICIAL", note: "A public matter" };
const SECRET_NOTE: PackItem = { ...NOTE_ITEM, id: "n2", marking: "SECRET", note: "A guarded matter" };

function pages(html: string): string[] {
  return html.split('<section class="page item"').slice(1);
}

describe("escapeHtml", () => {
  it("escapes the five characters that can open markup", () => {
    expect(escapeHtml(`<a href="x" onclick='y'>&`)).toBe("&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;");
  });
});

describe("packPrintHtml", () => {
  it("gives each item page its own marking, top and bottom, never the pack's level", () => {
    const html = packPrintHtml(manifest([OFFICIAL_NOTE, SECRET_NOTE], { mark: { ...manifest([]).mark, handling_level: "SECRET" } }));
    const [official, secret] = pages(html) as [string, string];
    expect(official.match(/class="banner banner-(top|bottom)">Marked OFFICIAL</g)).toHaveLength(2);
    expect(official).not.toContain("SECRET");
    expect(secret.match(/class="banner banner-(top|bottom)">Marked SECRET</g)).toHaveLength(2);
    expect(official.indexOf("banner-top")).toBeLessThan(official.indexOf("A public matter"));
    expect(official.indexOf("A public matter")).toBeLessThan(official.indexOf("banner-bottom"));
  });

  it("puts the withheld sentence on the cover only when withheld is a number above zero", () => {
    const sentence = "2 items in this pack are withheld from you.";
    expect(packPrintHtml(manifest([OFFICIAL_NOTE], { policy: "disclose", withheld: 2 }))).toContain(sentence);
    for (const withheld of [null, 0] as const) {
      expect(packPrintHtml(manifest([OFFICIAL_NOTE], { policy: "omit", withheld }))).not.toContain("withheld");
    }
    expect(packPrintHtml(manifest([OFFICIAL_NOTE], { withheld: undefined }))).not.toContain("withheld");
  });

  it("states the cover in words, including the mark and any retracted evidence", () => {
    const html = packPrintHtml(manifest([OFFICIAL_NOTE]));
    expect(html).toContain("Version 1, published 3 October 2026 by ana");
    expect(html).toContain("Exported by ben on 11 October 2026; handling level SECRET; OspreyFlow export led-1");
    expect(html).not.toContain("retracted");
    const flagged = packPrintHtml(manifest([OFFICIAL_NOTE], { mark: { ...manifest([]).mark, rests_on_retracted_evidence: true } }));
    expect(flagged).toContain("This pack rests on evidence since retracted or corrected.");
  });

  it("escapes every string it interpolates", () => {
    const hostile = "<script>alert(1)</script>";
    const html = packPrintHtml(
      manifest([{ ...OFFICIAL_NOTE, note: hostile, marking: `OFFICIAL"><script>x</script>` }], {
        title: hostile,
        published_by: hostile,
        ledger_entry_id: hostile,
        mark: { ...manifest([]).mark, exported_by: hostile, handling_level: hostile },
      }),
    );
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
  });

  it("escapes what a trend carries too", () => {
    const hostile = "<img src=x onerror=1>";
    const trend: PackItem = { ...TREND_ITEM, trend: { ...TREND_ITEM.trend!, definition: { ...TREND_ITEM.trend!.definition, title: hostile, measure_field: hostile }, result: { ...TREND_ITEM.trend!.result, points: [{ period_start: hostile, series: hostile, value: 1 }] } } };
    expect(packPrintHtml(manifest([trend]))).not.toContain("<img");
  });

  it("gives every item in the manifest a page, however many there are", () => {
    const many = Array.from({ length: 40 }, (_, i): PackItem => ({ ...OFFICIAL_NOTE, id: `n${i}`, note: `Note number ${i}` }));
    const html = packPrintHtml(manifest(many));
    expect(pages(html)).toHaveLength(40);
    expect(html).toContain("Note number 39");
    expect(html.match(/page-break-after: always/g)?.length).toBeGreaterThan(0);
  });

  it("prints every point of a trend, not a sample", () => {
    const rows = packPrintHtml(manifest([TREND_ITEM])).match(/<tr><td>/g);
    expect(rows).toHaveLength(TREND_ITEM.trend!.result.points.length);
  });
});
