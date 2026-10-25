// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { buildReportArtefact } from "./reportExport";
import type { Assumption, IntelligenceGap, Judgement } from "../../../../packages/schemas/generated";
import type { Yardstick } from "../assessment/api";
import type { ExportManifest, ExportMark } from "./api";

const MARK: ExportMark = {
  osprey_mark: "OspreyFlow",
  investigation_id: "inv-1",
  exported_at: "2026-09-23T00:00:00Z",
  resolution_threshold: 0.95,
  handling_level: "OFFICIAL",
};

const MANIFEST: ExportManifest = { policy: "disclose", withheld: true };

const YARDSTICK: Yardstick = {
  name: "default",
  bands: [{ label: "B4", lower: 0.55, upper: 0.7 }],
};

const JUDGEMENT: Judgement = {
  id: "j1",
  investigation_id: "inv-1",
  statement: "Mercer <script>alert(1)</script> is linked to Fixture Corp",
  probability_band: "B4",
  supporting: ["n1", "n2"],
  contradicting: [],
  author: "analyst-1",
  created_at: "2026-09-20T00:00:00Z",
};

const GAP: IntelligenceGap = {
  id: "g1",
  investigation_id: "inv-1",
  question: "What is the source of the Fixture Corp funding?",
  raised_by: "analyst-1",
  status: "open",
  created_at: "2026-09-21T00:00:00Z",
};

const ASSUMPTION: Assumption = {
  id: "a1",
  investigation_id: "inv-1",
  statement: "Fixture Corp's registered address is current",
  if_false_impact: "the resolved entity may be a shell",
  created_at: "2026-09-22T00:00:00Z",
};

describe("report export — test_report_export_produces_a_self_contained_html_document_carrying_the_mark", () => {
  it("produces a well-formed, self-contained HTML document", () => {
    const html = buildReportArtefact({
      judgements: [JUDGEMENT],
      gaps: [GAP],
      assumptions: [ASSUMPTION],
      yardstick: YARDSTICK,
      mark: MARK,
      manifest: MANIFEST,
    });

    expect(html.trim().startsWith("<!DOCTYPE html>")).toBe(true);
    const doc = new DOMParser().parseFromString(html, "text/html");
    expect(doc.querySelectorAll("parsererror")).toHaveLength(0);
    expect(doc.querySelector("style")).not.toBeNull();
    expect(doc.querySelector("link[rel=stylesheet]")).toBeNull();
    expect(doc.querySelector("script[src]")).toBeNull();
  });

  it("carries the mark both visibly (header/footer stamp) and as an embedded structured field", () => {
    const html = buildReportArtefact({
      judgements: [JUDGEMENT],
      gaps: [GAP],
      assumptions: [ASSUMPTION],
      yardstick: YARDSTICK,
      mark: MARK,
      manifest: MANIFEST,
    });
    const doc = new DOMParser().parseFromString(html, "text/html");

    const headerStamp = doc.querySelector("header.osprey-stamp")?.textContent ?? "";
    const footerStamp = doc.querySelector("footer.osprey-stamp")?.textContent ?? "";
    expect(headerStamp).toContain("OspreyFlow");
    expect(headerStamp).toContain("inv-1");
    expect(footerStamp).toContain("OspreyFlow");

    const embedded = doc.querySelector("script#osprey-export-mark")?.textContent ?? "";
    const parsedMark = JSON.parse(embedded);
    expect(parsedMark).toEqual(MARK);
  });

  it("escapes judgement content — no injected markup from a statement's own text", () => {
    const html = buildReportArtefact({
      judgements: [JUDGEMENT],
      gaps: [],
      assumptions: [],
      yardstick: YARDSTICK,
      mark: MARK,
      manifest: MANIFEST,
    });
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("renders every judgement/gap/assumption passed in — no cap, no silent truncation", () => {
    const manyJudgements = Array.from({ length: 50 }, (_, i) => ({
      ...JUDGEMENT,
      id: `j${i}`,
      statement: `judgement number ${i}`,
    }));
    const html = buildReportArtefact({
      judgements: manyJudgements,
      gaps: [],
      assumptions: [],
      yardstick: YARDSTICK,
      mark: MARK,
      manifest: MANIFEST,
    });
    for (const j of manyJudgements) {
      expect(html).toContain(j.statement);
    }
  });

  it("a disclosed manifest that says material is withheld renders the standing sentence, and no number", () => {
    const html = buildReportArtefact({
      judgements: [],
      gaps: [],
      assumptions: [],
      yardstick: YARDSTICK,
      mark: MARK,
      manifest: MANIFEST,
    });
    expect(html).toContain("This case holds material you are not cleared to see.");
    expect(html).not.toContain("hidden by handling");
  });

  it("renders nothing of the manifest when nothing is withheld, or when the deployment omits it", () => {
    for (const manifest of [
      { policy: "disclose", withheld: false },
      { policy: "omit", withheld: null },
      { policy: "omit", withheld: true },
    ] as const) {
      const html = buildReportArtefact({
        judgements: [],
        gaps: [],
        assumptions: [],
        yardstick: YARDSTICK,
        mark: MARK,
        manifest,
      });
      expect(html).not.toContain("not cleared to see");
    }
  });

  it("a document assembled without a mark is distinguishable from one that carries it — the negative control", () => {
    const html = buildReportArtefact({
      judgements: [],
      gaps: [],
      assumptions: [],
      yardstick: YARDSTICK,
      mark: MARK,
      manifest: MANIFEST,
    });
    const plainSummary = `<html><body>${JUDGEMENT.statement}</body></html>`;
    expect(html).toContain("osprey-export-mark");
    expect(plainSummary).not.toContain("osprey-export-mark");
  });
});

// 9 October 2026, the analyst journey's export: the report was titled by the case's id and cited
// its evidence as `content:69b2…` and `01M46CS…` — a reader of the report has neither the canvas
// nor the ids' meaning. It names the case, and each cited node as the canvas names it.
describe("a report names its case and its evidence", () => {
  const html = buildReportArtefact({
    judgements: [JUDGEMENT],
    gaps: [],
    assumptions: [],
    yardstick: YARDSTICK,
    mark: MARK,
    manifest: MANIFEST,
    caseName: "Analyst journey",
    citationLabel: (id) => ({ n1: "Person: MERCER, Dana", n2: "Document: Wing officer's note" })[id] ?? id,
  });
  const doc = new DOMParser().parseFromString(html, "text/html");

  it("is titled by the case's name", () => {
    expect(doc.title).toContain("Analyst journey");
    expect(doc.querySelector("h1")?.textContent).toContain("Analyst journey");
  });

  it("cites each piece of evidence by name, keeping its id only as data", () => {
    const citations = doc.querySelector(".judgement .citations")?.textContent ?? "";
    expect(citations).toContain("Person: MERCER, Dana");
    expect(citations).toContain("Document: Wing officer's note");
    expect(citations).not.toMatch(/\bn1\b|\bn2\b/);
    expect(doc.querySelector('[data-id="n2"]')).not.toBeNull();
  });
});
